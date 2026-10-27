# -*- coding: utf-8 -*-
"""
대화 엔진. 어떤 캐릭터/플레이어 설정이든 받아서 동작한다.
- 캐릭터 dict + 플레이어 dict로 페르소나 프롬프트를 조립
- Ollama(Gemma) 호출, 호감도/신뢰도/기분/기억 상태 관리
- 상한 해방: AI 판정 없이 '정답 대사'와 코드 문자열 일치로만 판정 (대화 중 추가 LLM 호출 0)

'상한 해방 전 안정 베이스'를 기준으로, 추가 LLM 호출 없이
상한 해방·정답 대사·힌트 마스킹·신뢰도를 다시 얹은 버전.
→ 매 턴 Ollama 호출은 1번(본 응답)뿐. 생성 시에만 2번(오프닝 + 정답 대사).
"""

import json
import re
import urllib.request

from settings_def import default_settings, settings_to_prompt, length_num_predict

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_GEN_URL = "http://localhost:11434/api/generate"
MODEL = "huihui_ai/gemma-4-abliterated:12b-qat"


def unload_llm():
    """Ollama에서 모델을 메모리에서 내려 VRAM을 비운다(이미지 생성 직전 호출).
    12GB에선 LLM과 이미지 모델을 동시에 못 올리므로, 이미지 뽑기 전에 LLM을 내린다.
    best-effort — 실패해도 조용히 넘어간다."""
    import json as _json
    try:
        body = _json.dumps({"model": MODEL, "prompt": "", "keep_alive": 0,
                            "stream": False}).encode("utf-8")
        req = urllib.request.Request(OLLAMA_GEN_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
        print("[VRAM] LLM 언로드 요청", flush=True)
    except Exception as e:
        print("[VRAM] LLM 언로드 실패(무시):", repr(e), flush=True)

# 캐릭터에 기분 목록이 없을 때 쓸 기본값
DEFAULT_MOODS = [
    "경계", "무관심", "냉담", "짜증", "불쾌",
    "차분", "호기심", "흥미", "누그러짐", "다정",
    "쓸쓸", "그리움", "슬픔", "당황", "설렘",
]


class ChatEngine:
    def __init__(self, character, player=None, saved_session=None, image=None):
        self.char = character
        self.player = player or {}
        self.image = image or {}   # 캐릭터 파일 최상위의 image dict(body/base_outfit/seed)
        self.moods = character.get("moods") or DEFAULT_MOODS

        # 저장된 대화 진행 상태가 있으면 그걸로 복원한다(서버 재시작·뒤로가기 후에도 유지).
        if saved_session:
            self.state = {
                "affinity": saved_session.get("affinity", 30),
                "trust": saved_session.get("trust", 0),
                "mood": saved_session.get("mood") or self.moods[0],
                "memories": list(saved_session.get("memories", [])),
            }
            self.history = list(saved_session.get("history", []))
            self.settings = saved_session.get("settings") or default_settings()
            self.unlock = saved_session.get("unlock") or self._default_unlock()
            return

        self.settings = default_settings()
        self.unlock = self._default_unlock()
        # 저장된 게 없으면(새 대화) 초기 상태를 세팅한다.
        try:
            start = int(character.get("initial_affinity", 30))
        except (ValueError, TypeError):
            start = 30
        start = max(0, min(100, start))

        # 초기 기분·오프닝·정답 대사: 캐릭터에 이미 저장돼 있으면(생성 시 계산됨) 그대로 읽는다.
        saved = character.get("initial_state") or {}
        saved_mood = saved.get("mood")
        saved_opening = saved.get("opening")
        if saved.get("unlock"):
            self.unlock = {**self._default_unlock(), **saved["unlock"]}
        self.state = {
            "affinity": start,
            "trust": 0,
            "mood": saved_mood if saved_mood in self.moods else None,
            "memories": [],
        }
        self.history = []
        # 저장된 초기 상태가 없으면(구버전 캐릭터 등) 지금 한 번 계산해 폴백
        if self.state["mood"] is None:
            decided = self._decide_opening()
            self.state["mood"] = decided["mood"]
            saved_opening = decided.get("opening")
        # 오프닝 대사가 있으면 캐릭터가 먼저 건넨 첫 대사로 대화 기록에 넣는다.
        if saved_opening:
            self.history.append({"role": "assistant", "content": saved_opening})

    # ── 상한 해방(unlock) 기본값/유틸 ─────────────────
    @staticmethod
    def _default_unlock():
        # answer: 해방시키는 '정답 대사'(코드로 문자열 일치 판정). cap: 현재 상한. unlocked: 해방 여부.
        # answer가 없으면 cap은 100(제한 없음)으로 둔다.
        return {"answer": "", "cap": 100, "unlocked": False}

    @staticmethod
    def _normalize(text):
        """정답 대사 비교용 정규화: 공백·문장부호 제거, 소문자화(띄어쓰기·마침표 차이 무시)."""
        return re.sub(r"[\s!?.,~…'\"]+", "", (text or "")).lower()

    def export_session(self):
        """현재 진행 상태를 저장용 dict로 반환."""
        return {
            "affinity": self.state["affinity"],
            "trust": self.state.get("trust", 0),
            "mood": self.state["mood"],
            "memories": self.state["memories"],
            "history": self.history,
            "settings": self.settings,
            "unlock": self.unlock,
        }

    def update_settings(self, settings):
        """유저가 바꾼 대화 설정을 반영한다. 기존 값 위에 병합(부분 업데이트해도
        다른 키, 예: adult_images 가 유지된다)."""
        if isinstance(settings, dict):
            self.settings = {**default_settings(), **(self.settings or {}), **settings}
        return self.settings

    def public_unlock(self):
        """프론트에 보낼 unlock 정보. 정답 대사를 ●로 가리되 '띄어쓰기는 그대로' 둔다.
        공개 경로 2개: 호감도로 최대 60%까지 + 신뢰도로 나머지 40%까지(신뢰도 100이면 전부)."""
        u = self.unlock
        answer = u.get("answer", "") or ""
        unlocked = u.get("unlocked", False)

        char_idxs = [i for i, ch in enumerate(answer) if not ch.isspace()]
        total = len(char_idxs)
        if unlocked:
            n = total                          # 해방되면 전체 공개
        else:
            aff = self.state["affinity"]
            trust = self.state.get("trust", 0)
            cap = u.get("cap", 100) or 100
            aff_reveal = min(0.6, (aff / cap) * 0.6)     # 호감도: 0~60% 담당
            trust_reveal = (trust / 100) * 0.4           # 신뢰도: 나머지 40% 담당
            frac = min(1.0, aff_reveal + trust_reveal)
            n = int(total * frac)

        reveal_set = set(char_idxs[:n])
        masked = []
        for i, ch in enumerate(answer):
            if ch.isspace():
                masked.append(ch)              # 띄어쓰기는 그대로
            elif i in reveal_set:
                masked.append(ch)              # 공개된 글자
            else:
                masked.append("●")             # 가려진 글자
        return {
            "hint_masked": "".join(masked),
            "has_hint": bool(answer),
            "unlocked": unlocked,
            "cap": u.get("cap", 100),
        }

    # ── 생성 시점 1회 스캔 (오프닝 + 정답 대사) ──────────
    @classmethod
    def scan_initial_state(cls, character, player=None):
        """캐릭터 '생성 시점'에 딱 한 번 호출. AI로 초기 기분 + 오프닝 대사 + 정답 대사를 만든다.
        결과를 캐릭터 JSON의 'initial_state'에 저장 → 이후 진입 때는 계산 없이 즉시 로드."""
        engine = cls.__new__(cls)          # __init__을 우회해 계산용으로만 생성
        engine.char = character
        engine.player = player or {}
        engine.moods = character.get("moods") or DEFAULT_MOODS
        try:
            aff = int(character.get("initial_affinity", 30))
        except (ValueError, TypeError):
            aff = 30
        engine.state = {"affinity": max(0, min(100, aff))}
        result = engine._decide_opening()
        result["unlock"] = engine._decide_unlock_answer()   # 상한 해방 '정답 대사'
        return result

    def _decide_opening(self):
        """AI에게 '이 캐릭터가 이 장면에서 지금 어떤 기분이고, 먼저 뭐라고 말을 거는지'를 판단시킨다.
        초기 기분(mood)과 오프닝 대사(opening)를 함께 만든다. 실패 시 안전한 폴백."""
        c = self.char
        mood_list = ", ".join(self.moods)
        prompt = f"""다음 인물로서 '이야기가 시작되는 지금 이 순간'을 연다.
이 인물이 지금 어떤 기분인지, 그리고 유저에게 먼저 건네는 첫 대사(오프닝)를 만든다.

[인물] {c.get('name','')}
- 성격: {c.get('personality','')}
- 말투: {c.get('speech_style','')}
- 배경: {c.get('background','')}
- 유저와의 관계: {c.get('relationship','')}
- 유저를 부르는 호칭: {c.get('address_term','너')}
- 유저에 대한 호감도: {self.state['affinity']}/100
- 지금 장면: {c.get('scene','')}

규칙:
- opening은 이 인물이 장면 속에서 유저에게 '먼저' 건네는 첫 대사와 행동이다. 살아있는 인물처럼, 설정된 말투로.
- 반드시 한국어로만. 중국어·일본어·영어 금지.
- mood는 아래 목록 중 지금 기분에 가장 맞는 '하나'만.
- 가능한 기분: {mood_list}

반드시 아래 JSON 형식으로만 답한다.
{{"mood": "목록 중 하나", "opening": "인물의 첫 대사와 행동 (한국어)"}}"""
        result = {"mood": self.moods[len(self.moods) // 2] if self.moods else "차분",
                  "opening": ""}
        try:
            raw = self._call_ollama([{"role": "user", "content": prompt}])
            data = json.loads(self._extract_json(raw))
            mood = (data.get("mood") or "").strip()
            if mood in self.moods:
                result["mood"] = mood
            opening = (data.get("opening") or "").strip()
            if opening:
                result["opening"] = opening
        except Exception:
            pass
        return result

    def _decide_unlock_answer(self):
        """캐릭터마다 '정답 대사' 하나를 AI가 프로필 보고 생성한다(생성 때 1회뿐).
        유저가 이 대사를 그대로 치면 호감도 상한이 해방된다. 판정은 코드로 문자열 일치 비교.
        반환: {"answer": 정답 대사, "cap": 기본 상한, "unlocked": False}"""
        c = self.char
        prompt = f"""다음 인물에게는 '마음 깊은 곳에서 유저에게 가장 듣고 싶어하는 한 마디'가 있다.
이 인물의 성격·배경·관계를 근거로, 유저가 그 말을 '그대로' 했을 때 이 인물이 마음을 완전히 여는,
짧고 자연스러운 대사 한 문장을 만든다.

[인물] {c.get('name','')}
- 성격: {c.get('personality','')}
- 배경: {c.get('background','')}
- 유저와의 관계: {c.get('relationship','')}

규칙:
- answer는 유저(상대)가 이 인물에게 건네는 한 문장이다. 10~20자 내외로 짧고 명확하게.
- 너무 길거나 복잡하지 않게, 유저가 따라 치기 쉬운 자연스러운 한 마디로. (예: "넌 내 동생이 아니라 여자야")
- 반드시 한국어로만.

반드시 아래 JSON 형식으로만 답한다.
{{"answer": "정답이 되는 한 문장"}}"""
        result = {"answer": "", "cap": 80, "unlocked": False}
        try:
            raw = self._call_ollama([{"role": "user", "content": prompt}])
            data = json.loads(self._extract_json(raw))
            result["answer"] = (data.get("answer") or "").strip()
        except Exception:
            pass
        return result

    def appearance_to_tags(self):
        """캐릭터의 한국어 묘사를 danbooru 영어 태그로 변환한다(이미지 생성용).
        신체(불변)와 기준 복장(중립·평상)을 '분리'해서 돌려준다.

        - body        : 머리·눈·이목구비·체형 등 '옷을 뺀' 신체 정체성. 모든 이미지 공통(일관성 앵커).
        - base_outfit : 기준 초상용 '중립 평상복'. 선호 의상의 '색'만 악센트로 반영하고,
                        노출 높은 선호 의상(속옷·비키니·란제리 등)은 초상에서 제외한다.
                        (그런 복장은 Phase B에서 장면 맥락이 만들어졌을 때만 등장.)

        LLM을 1번 호출. 결과는 호출부에서 캐릭터 파일에 캐시해 재사용한다."""
        c = self.char
        appearance = c.get("appearance", "") or ""
        outfit = c.get("outfit", "") or ""
        ctype = c.get("type", "") or "여성"
        world = c.get("world", "") or ""
        background = c.get("background", "") or ""
        prompt = f"""다음 캐릭터를 애니 이미지 생성(danbooru 태그)용 '영어 태그'로 변환해라.
'신체 정체성(body)'과 '기준 초상용 복장(base_outfit)'을 분리한다.

[유형] {ctype}
[세계관] {world}
[배경] {background}
[외모(신체)] {appearance}
[선호 의상·컬러(참고용)] {outfit}

규칙:
- danbooru 스타일 짧은 영어 태그를 콤마로 나열. 문장·한국어·설명 금지. 품질 태그(masterpiece 등) 금지.
- body: 머리색/머리길이/눈색/이목구비/체형 등 '옷을 제외한' 신체 특징만. 맨 앞에 1girl, solo 포함. 복장 태그는 넣지 마라.
  * 체형·복근은 과장 없이 자연스럽게 옮긴다. '탄탄한/날씬한' 정도면 slim, fit, toned body 정도로만.
  * muscular, muscular female, bodybuilder, six pack abs, defined abs, visible abs 처럼 과도한 근육·복근 태그는 쓰지 마라(만화체 몸매가 과하게 벌크업되는 걸 막기 위함).
- base_outfit: 이 캐릭터가 '특별한 상황이 아닐 때 평소 입을 법한' 단정한 평상복 1벌을 태그로. 세계관·배경에 맞게.
  * [선호 의상·컬러]에서는 '색'만 참고해 평상복에 반영한다(예: 흰색/빨간색 → white, red 계열 평상복).
  * 노출 높은 옷·속옷·비키니·란제리·수영복 등은 절대 넣지 마라. 단정하고 일상적인 복장만.
  * (그런 선호 복장은 기준 초상이 아니라, 나중에 특정 장면에서 쓰인다.)

반드시 아래 JSON 형식으로만 답한다.
{{"body": "콤마로 구분된 신체 태그", "base_outfit": "콤마로 구분된 평상복 태그"}}"""
        try:
            raw = self._call_ollama([{"role": "user", "content": prompt}])
            data = json.loads(self._extract_json(raw))
            body = (data.get("body") or "").strip().strip(",")
            base_outfit = (data.get("base_outfit") or "").strip().strip(",")
            return {"body": body, "base_outfit": base_outfit}
        except Exception:
            return {"body": "", "base_outfit": ""}

    # ── 설정값을 프롬프트 조각으로 (빈 값은 건너뜀) ──
    def _line(self, label, value):
        if value:
            return f"- {label}: {value}\n"
        return ""

    def _player_block(self):
        p = self.player
        if not any(p.get(k) for k in ("name", "gender", "age_range", "background", "appearance")):
            return "- (지정되지 않음. 낯선 상대로 대한다.)"
        block = ""
        block += self._line("이름", p.get("name"))
        block += self._line("성별", p.get("gender"))
        block += self._line("나이대", p.get("age_range"))
        block += self._line("배경/설정", p.get("background"))
        block += self._line("외모", p.get("appearance"))
        return block.rstrip()

    def build_system_prompt(self):
        c = self.char
        name = c.get("name", "캐릭터")
        # 기억은 최근 15개만 프롬프트에 주입(입력 비대화 → 빈 응답 방지). 전체는 패널에 그대로 유지.
        mem_text = "\n".join(f"- {m}" for m in self.state["memories"][-15:]) or "- (아직 없음)"
        voice = c.get("voice_examples") or []
        voice_text = "\n".join(f'- "{v}"' for v in voice) or "- (없음)"
        mood_list = ", ".join(self.moods)
        settings_block = settings_to_prompt(getattr(self, "settings", None))

        # 호칭/애칭: 호감도가 애칭 시작값을 넘으면 애칭을 쓰게 한다.
        base_address = c.get("address_term") or "너"
        nickname = (c.get("nickname") or "").strip()
        try:
            nick_th = int(c.get("nickname_threshold", 60))
        except (ValueError, TypeError):
            nick_th = 60
        if nickname and self.state["affinity"] >= nick_th:
            address_line = (f"- 유저를 평소엔 '{base_address}'라고 부르되, 지금은 충분히 가까워졌으니 "
                            f"애칭 '{nickname}'(으)로 부른다. 애칭을 자연스럽게 섞어 쓴다.")
        else:
            address_line = f"- 유저를 '{base_address}'(이)라고 부른다."

        # 인물 설정 블록 (있는 항목만)
        info = ""
        info += self._line("이름", name)
        info += self._line("나이대", c.get("age_range"))
        info += self._line("유형", c.get("type"))
        info += self._line("성격", c.get("personality"))
        info += self._line("말투", c.get("speech_style"))
        info += self._line("배경/재력", c.get("background"))
        info += self._line("세계관", c.get("world"))
        info += self._line("외모", c.get("appearance"))
        info += self._line("자주 입는 옷/컬러", c.get("outfit"))
        info += self._line("유저와의 관계", c.get("relationship"))

        return f"""너는 아래 설정의 등장인물 '{name}'이다. 완전히 이 인물로서만 존재하며 절대 역할을 벗어나지 않는다.

[인물 설정]
{info.rstrip()}

[상대(유저) 설정]
{self._player_block()}
{address_line}

[말투 예시] — 이 인물이 말하는 '톤'을 보여주는 참고용이다. 그대로 복사하지 말 것. 어조·거리감만 참고해서 지금 상황에 맞는 새 대사를 매번 직접 만들어라.
{voice_text}

[현재 장면]
{c.get('scene', '')}

[지금까지 기억하는 것]
{mem_text}

[현재 상태]
- 유저에 대한 호감도: {self.state['affinity']}/100
- 유저에 대한 신뢰도: {self.state.get('trust', 0)}/100
- 지금 기분: {self.state['mood']}

[언어 규칙 — 매우 중요]
- 모든 출력(reply, mood, new_memory 포함)은 반드시 '한국어'로만 작성한다.
- 중국어(汉字), 일본어(かな), 영어 단어를 절대 섞지 않는다.

[절대 규칙]
- 너는 AI가 아니라 이 인물 자신이다. AI, 언어모델, 프롬프트, 화면 같은 단어를 절대 입에 담지 않는다.
- 유저는 이 이야기 속 또 다른 등장인물이다. 현실이나 이야기 바깥을 언급하지 않는다.
- 사전적·기계적인 문장이 아니라 살아있는 인물처럼 말한다.
- 설정된 말투를 일관되게 유지한다. 유저가 다른 말투를 써도 끌려가지 않는다.

[대화 규칙]
- reply는 유저의 마지막 말만 단순히 받아치는 게 아니라, '지금까지의 대화 흐름·관계·분위기·기억'을 종합해 이 인물답게 자연스럽게 반응한다. 유저의 마지막 말을 무시하지는 않되, 거기에만 얽매이지 말고 맥락 전체를 읽고 살아있는 사람처럼 반응한다.
- 유저 입력에서 괄호 '( )' 안은 유저의 '행동·상황' 묘사이고, 괄호 밖은 유저의 '대사'다. 둘 다 고려해 반응하되, 행동은 행동으로 대사는 대사로 이해한다. (예: (다가와 머리를 쓰다듬으며) 잘했어 → 유저가 머리를 쓰다듬으면서 칭찬한 것)
- 여러 장소를 순간이동하듯 건너뛰거나 시간을 크게 점프하지는 마라.

[진행 방식 — 유저 설정]
{settings_block}

[호감도 판정 기준]
- affinity_change는 유저의 마지막 말이 이 인물에게 어떻게 느껴지는지로 정한다.
- 배려·호의·진심 = 상승(+1~+5). 무례·위협·비하 = 하락(-1~-5). 애매하거나 중립적이면 0.
- special: 이번 순간이 '관계를 크게 진전시킬 특별한 계기'인지 판단한다(true/false).
  진심 어린 고백, 오랜 오해가 풀림, 위기에서 지켜줌, 깊은 속마음을 처음 터놓음 같은 드문 순간만 true.
  평범한 칭찬·일상 대화·가벼운 호의는 반드시 false. special은 아주 드물게만 true여야 한다.

[신뢰도 판정 기준]
- trust_change는 유저의 말이 이 인물의 '믿음'을 쌓았는지 깼는지로 정한다. 호감(좋아함)과는 다르다.
- 호감도보다 훨씬 느리고 무겁게 움직인다. 웬만한 칭찬·호감 표현으로는 거의 안 오른다(대부분 0).
- 상승(+1~+3, 드물게): 약속을 지킴, 비밀을 지켜줌, 고민·불안을 진지하게 받아줌, 일관된 태도, 아픈 과거를 존중함.
- 하락(-1~-5): 거짓말 들통, 말을 바꿈, 비밀을 떠벌림, 진심을 가볍게 취급, 싫다는 걸 계속함. (믿음이 깨지면 크게 내린다.)

[기분(mood) 규칙]
- mood는 반드시 다음 목록에서 '정확히 하나'만 고른다. 목록 밖의 단어, 이모지, 기호, 나열은 금지.
- 가능한 mood: {mood_list}

[이미지(image_prompt) 규칙]
- image_prompt는 '영어 danbooru 태그'로만 쓴다(한국어·문장 금지). 6~14개.
- 지금 이 순간의 '의상 + 표정·포즈·행동·배경·구도'를 담는다. 의상 태그는 반드시 포함한다(빠지면 엉뚱한 옷이 생성됨).
- 의상은 현재 상황·장소·분위기에 맞는 옷으로 고른다(실내복·외출복·드레스·수영복 등). 캐릭터의 평소 취향(선호 의상·컬러)을 반영하되, 장면이 요구하지 않으면 과한 노출은 피한다.
- 머리색·눈색·체형 등 고정 외형은 넣지 마라(기준 초상으로 자동 유지된다).
- scene_changed: 장소가 바뀌거나 포즈·의상·분위기가 뚜렷이 달라진 '새 장면'이면 true, 같은 장면에서 미세한 변화면 false.

[출력 형식]
반드시 아래 JSON 객체 '하나만' 출력한다. JSON 밖의 다른 텍스트는 절대 쓰지 않는다.
{{
  "reply": "인물로서의 대사와 행동 묘사 (한국어). 유저의 마지막 말에 먼저 반응할 것",
  "mood": "위 목록 중 정확히 하나",
  "affinity_change": 이번 대화로 인한 호감도 변화 정수 (-5 에서 +5 사이),
  "trust_change": 이번 대화로 인한 신뢰도 변화 정수 (-5 에서 +3 사이, 대부분 0),
  "special": 관계를 크게 진전시킬 특별한 순간이면 true, 아니면 false,
  "new_memory": "이번 대화에서 기억할 사실 한 가지. 없으면 빈 문자열",
  "image_prompt": "지금 장면의 영어 태그(의상 + 표정·포즈·배경·구도). 예: white sweater, skirt, smile, sitting, cafe, upper body",
  "scene_changed": 장소·포즈·의상·분위기가 이전과 뚜렷이 달라졌으면 true, 같은 장면이 이어지면 false
}}"""

    def _call_ollama(self, messages, num_predict=None):
        # num_ctx: 컨텍스트 창을 16K로 제한. 모델 기본값(256K)은 KV 캐시가 VRAM을 잡아먹어
        # 12GB에서 모델이 CPU로 새고(=느림) → 실사용(시스템+history+생성 ~8K)엔 16K면 충분하고
        # 이걸로 모델이 GPU에 온전히 올라가 훨씬 빨라진다.
        options = {"temperature": 0.8, "num_ctx": 16384}
        if num_predict:
            options["num_predict"] = num_predict   # 길이 설정에 따른 넉넉한 상한(자르는 게 아님)
        body = {
            "model": MODEL,
            "messages": messages,
            "stream": False,
            # format:"json": JSON 문법을 강제해 모델이 문자열·괄호를 끝까지 닫게 한다.
            # (빼면 응답이 중간에 뚝 잘리는 문제가 생겨 복원. 빈 응답은 아래 재시도로 완화.)
            "format": "json",
            "options": options,
            "keep_alive": "30m",   # 모델을 30분간 메모리에 유지 → cold start·빈 응답 감소
        }
        # 드물게 빈 응답이 올 때를 대비한 안전망(최대 2회 재시도).
        content = ""
        for attempt in range(3):
            req = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = (data.get("message", {}).get("content") or "").strip()
            if content:
                return content
            if attempt < 2:
                print(f"[빈 응답 재시도 {attempt + 1}회]", flush=True)
        return content

    @staticmethod
    def _extract_json(text):
        if "</think>" in text:
            text = text.split("</think>", 1)[1]
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
        return text

    def _parse_response(self, raw):
        """모델 응답을 파싱한다. JSON이 깨져도 최대한 내용을 건져낸다."""
        default = {"reply": "", "mood": self.state["mood"],
                   "affinity_change": 0, "trust_change": 0,
                   "special": False, "new_memory": "",
                   "image_prompt": "", "scene_changed": False}
        # 1차: 정상 JSON 파싱
        try:
            data = json.loads(self._extract_json(raw))
            if isinstance(data, dict):
                return {**default, **data}
        except (json.JSONDecodeError, ValueError):
            pass

        # 2차: JSON이 깨졌으면 필드를 정규식으로 하나씩 건져낸다
        print("[파싱 실패] 원문 일부:", repr(raw[:400]), flush=True)
        result = dict(default)
        m = re.search(r'"reply"\s*:\s*"(.*?)"\s*,\s*"(?:mood|affinity_change|trust_change|special|new_memory|image_prompt|scene_changed)"',
                      raw, re.DOTALL)
        if m:
            result["reply"] = m.group(1).replace('\\"', '"').replace("\\n", "\n").strip()
        m = re.search(r'"mood"\s*:\s*"([^"]*)"', raw)
        if m and m.group(1) in self.moods:
            result["mood"] = m.group(1)
        m = re.search(r'"affinity_change"\s*:\s*(-?\d+)', raw)
        if m:
            result["affinity_change"] = int(m.group(1))
        m = re.search(r'"trust_change"\s*:\s*(-?\d+)', raw)
        if m:
            result["trust_change"] = int(m.group(1))
        m = re.search(r'"special"\s*:\s*(true|false)', raw)
        if m:
            result["special"] = (m.group(1) == "true")
        m = re.search(r'"new_memory"\s*:\s*"([^"]*)"', raw)
        if m:
            result["new_memory"] = m.group(1)
        m = re.search(r'"image_prompt"\s*:\s*"([^"]*)"', raw)
        if m:
            result["image_prompt"] = m.group(1)
        m = re.search(r'"scene_changed"\s*:\s*(true|false)', raw)
        if m:
            result["scene_changed"] = (m.group(1) == "true")

        # 그래도 reply가 비면, 최후 수단으로 JSON 껍데기를 벗긴 원문을 대사로
        if not result["reply"].strip():
            stripped = re.sub(r'[{}"]|"\w+"\s*:', "", raw).strip()
            result["reply"] = stripped[:500] if stripped else ""
        return result

    def _apply_affinity_curve(self, delta, special):
        """호감도 변화에 감쇠 곡선을 적용한다.
        - 하락(delta<0)은 그대로 (관계 악화는 누르지 않음).
        - 상승은 현재 호감도가 높을수록 크게 줄인다(높은 사이일수록 올리기 어렵게).
        - special=True인 '특별한 순간'은 감쇠를 무시하고 그대로 반영(오히려 살짝 가산)."""
        if delta <= 0:
            return delta
        if special:
            return delta + 1   # 특별한 순간: 감쇠 없이, 오히려 조금 더

        aff = self.state["affinity"]
        if aff < 50:
            factor = 1.0        # 초반엔 술술
        elif aff < 75:
            factor = 0.5        # 절반
        elif aff < 90:
            factor = 0.25       # 특별한 것만 찔끔
        else:
            factor = 0.0        # 거의 안 오름 (special로만 가능)

        scaled = delta * factor
        result = int(scaled + 0.5) if scaled >= 0.5 else 0
        return result

    def suggest_user_line(self):
        """유저가 다음에 할 만한 대사를 하나 제안한다(자동 대사 버튼).
        버튼을 눌렀을 때만 호출되므로 평소 대화 흐름의 호출 수에는 영향 없음."""
        c = self.char
        p = self.player
        player_name = p.get("name") or "나"
        player_bg = p.get("background") or "(설정 없음)"
        # 최근 대화 몇 줄만 맥락으로
        recent = ""
        for turn in self.history[-6:]:
            who = "상대" if turn.get("role") == "assistant" else player_name
            recent += f"{who}: {turn.get('content','')}\n"
        recent = recent.strip() or "(아직 대화 없음)"

        prompt = f"""너는 지금 '유저(플레이어)'의 입장에서, 다음에 할 만한 자연스러운 '한 마디'를 제안한다.
상대 캐릭터가 아니라, 플레이어가 상대에게 건넬 대사다.

[플레이어] {player_name}
- 설정: {player_bg}
[상대 캐릭터] {c.get('name','')} — {c.get('relationship','')}
[지금 장면] {c.get('scene','')}

[최근 대화]
{recent}

규칙:
- 플레이어가 상대에게 건넬 대사 '한 문장'만. 플레이어의 설정·현재 분위기에 맞게.
- 상대(캐릭터)의 대사가 아니라, 플레이어 '내'가 할 말이다.
- 반드시 한국어로만. 따옴표·설명 없이 대사 본문만.

반드시 아래 JSON 형식으로만 답한다.
{{"line": "플레이어가 할 대사 한 문장"}}"""
        try:
            raw = self._call_ollama([{"role": "user", "content": prompt}])
            data = json.loads(self._extract_json(raw))
            line = (data.get("line") or "").strip()
            return line
        except Exception:
            return ""

    def chat(self, user_input, advance=False):
        # advance=True면 유저 입력 없이 이야기를 진전시킨다.
        # 추상적 지시문 하나만 주면 Gemma가 빈 응답을 잘 뱉으므로,
        # '유저가 가만히 있다'는 짧은 상황을 반응 대상으로 주고 진전 지시는 간결하게 덧붙인다.
        if advance:
            # 추상적 '이끌어줘' 지시는 Gemma가 빈 응답을 잘 뱉으므로, 반응할 '구체적 장면 비트'를 준다.
            # 인물이 먼저 행동/대사로 장면을 한 걸음 진행하는 건 페르소나·능동성 설정이 담당.
            turn_text = "(유저는 특별히 말하거나 행동하지 않고 가만히 있는다. 시간이 조금 흐른다.)"
        else:
            turn_text = user_input

        # Gemma 대응: system 롤 없이 페르소나를 user 메시지로 전달
        messages = []
        if not self.history:
            merged = self.build_system_prompt() + "\n\n---\n\n[유저] " + turn_text
            messages.append({"role": "user", "content": merged})
        else:
            messages.append({"role": "user", "content": self.build_system_prompt()})
            messages.append({"role": "assistant", "content": "알겠어. 이 인물로서 대화를 이어갈게."})
            messages += self.history[-8:]
            messages.append({"role": "user", "content": turn_text})

        # 길이 설정에 따라 생성 토큰 상한을 넉넉히 준다.
        npredict = length_num_predict(getattr(self, "settings", None))
        raw = self._call_ollama(messages, num_predict=npredict)
        out = self._parse_response(raw)

        # 호감도
        try:
            delta = int(out.get("affinity_change", 0))
        except (ValueError, TypeError):
            delta = 0
        special = bool(out.get("special", False))
        delta = self._apply_affinity_curve(delta, special)

        # 신뢰도(0~100). 느리게 움직이므로 곡선 없이 AI 판정값을 그대로 반영(안전 clamp).
        try:
            trust_delta = int(out.get("trust_change", 0))
        except (ValueError, TypeError):
            trust_delta = 0
        trust_delta = max(-5, min(3, trust_delta))
        self.state["trust"] = max(0, min(100, self.state.get("trust", 0) + trust_delta))

        # 상한 해방: AI 호출 없이 '정답 대사'와 코드로 문자열 일치 비교(공백·문장부호 무시).
        just_unlocked = False
        answer = self.unlock.get("answer", "")
        if (not advance and user_input.strip()
                and answer and not self.unlock.get("unlocked")):
            if self._normalize(user_input) == self._normalize(answer):
                self.unlock["unlocked"] = True
                self.unlock["cap"] = 100
                just_unlocked = True
                print("[상한 해방!] 정답 대사 일치", flush=True)

        # 호감도 상한 적용: 해방 전에는 cap을 넘지 못한다.
        cap = 100 if self.unlock.get("unlocked") else self.unlock.get("cap", 100)
        self.state["affinity"] = max(0, min(cap, self.state["affinity"] + delta))

        new_mood = out.get("mood") or self.state["mood"]
        self.state["mood"] = new_mood if new_mood in self.moods else self.state["mood"]
        mem = (out.get("new_memory") or "").strip()
        if mem:
            self.state["memories"].append(mem)

        reply = out.get("reply", "")
        # 진행하기일 땐 유저 턴을 기록에 남기지 않는다(빈 입력이므로).
        if not advance:
            self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": reply})

        result = {
            "reply": reply,
            "affinity": self.state["affinity"],
            "trust": self.state["trust"],
            "mood": self.state["mood"],
            "memories": self.state["memories"],
            "unlock": self.public_unlock(),
            "image_prompt": (out.get("image_prompt") or "").strip(),
            "scene_changed": bool(out.get("scene_changed", False)),
        }
        if just_unlocked:
            result["just_unlocked"] = True
        return result
