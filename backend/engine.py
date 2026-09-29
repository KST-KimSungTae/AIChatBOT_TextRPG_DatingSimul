# -*- coding: utf-8 -*-
"""
대화 엔진. 이제 특정 캐릭터에 고정되지 않고, 어떤 캐릭터/플레이어 설정이든 받아서 동작한다.
- 캐릭터 dict + 플레이어 dict로 페르소나 프롬프트를 조립
- Ollama(Gemma) 호출, 호감도/기분/기억 상태 관리
캐릭터별로 ChatEngine 인스턴스를 하나씩 두면 세션이 분리된다(main.py가 관리).
"""

import json
import re
import urllib.request

from settings_def import default_settings, settings_to_prompt, length_num_predict

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "huihui_ai/gemma-4-abliterated:12b-qat"

# 캐릭터에 기분 목록이 없을 때 쓸 기본값
DEFAULT_MOODS = [
    "경계", "무관심", "냉담", "짜증", "불쾌",
    "차분", "호기심", "흥미", "누그러짐", "다정",
    "쓸쓸", "그리움", "슬픔", "당황", "설렘",
]


class ChatEngine:
    def __init__(self, character, player=None, saved_session=None):
        self.char = character
        self.player = player or {}
        self.moods = character.get("moods") or DEFAULT_MOODS

        # 저장된 대화 진행 상태가 있으면 그걸로 복원한다(서버 재시작·뒤로가기 후에도 유지).
        if saved_session:
            self.state = {
                "affinity": saved_session.get("affinity", 30),
                "mood": saved_session.get("mood") or self.moods[0],
                "memories": list(saved_session.get("memories", [])),
            }
            self.history = list(saved_session.get("history", []))
            self.settings = saved_session.get("settings") or default_settings()
            return

        self.settings = default_settings()
        # 저장된 게 없으면(새 대화) 초기 상태를 세팅한다.
        try:
            start = int(character.get("initial_affinity", 30))
        except (ValueError, TypeError):
            start = 30
        start = max(0, min(100, start))

        # 초기 기분·오프닝: 캐릭터에 이미 저장돼 있으면(생성 시 계산됨) 그대로 읽어 즉시 시작한다.
        saved = character.get("initial_state") or {}
        saved_mood = saved.get("mood")
        saved_opening = saved.get("opening")
        self.state = {
            "affinity": start,
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

    def export_session(self):
        """현재 진행 상태를 저장용 dict로 반환."""
        return {
            "affinity": self.state["affinity"],
            "mood": self.state["mood"],
            "memories": self.state["memories"],
            "history": self.history,
            "settings": self.settings,
        }

    def update_settings(self, settings):
        """유저가 슬라이더로 바꾼 대화 설정을 반영한다."""
        if isinstance(settings, dict):
            self.settings = {**default_settings(), **settings}
        return self.settings

    @classmethod
    def scan_initial_state(cls, character, player=None):
        """캐릭터 '생성 시점'에 딱 한 번 호출. AI로 초기 기분 + 오프닝 대사를 만들어 dict로 돌려준다.
        이 결과를 캐릭터 JSON의 'initial_state'에 저장 → 이후 진입 때는 계산 없이 즉시 로드."""
        engine = cls.__new__(cls)          # __init__을 우회해 계산용으로만 생성
        engine.char = character
        engine.player = player or {}
        engine.moods = character.get("moods") or DEFAULT_MOODS
        try:
            aff = int(character.get("initial_affinity", 30))
        except (ValueError, TypeError):
            aff = 30
        engine.state = {"affinity": max(0, min(100, aff))}
        return engine._decide_opening()

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
        mem_text = "\n".join(f"- {m}" for m in self.state["memories"]) or "- (아직 없음)"
        voice = c.get("voice_examples") or []
        voice_text = "\n".join(f'- "{v}"' for v in voice) or "- (없음)"
        mood_list = ", ".join(self.moods)
        address = c.get("address_term") or "너"
        settings_block = settings_to_prompt(getattr(self, "settings", None))

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
- 유저를 '{address}'(이)라고 부른다.

[말투 예시] — 이 인물이 말하는 '톤'을 보여주는 참고용이다. 그대로 복사하지 말 것. 어조·거리감만 참고해서 지금 상황에 맞는 새 대사를 매번 직접 만들어라.
{voice_text}

[현재 장면]
{c.get('scene', '')}

[지금까지 기억하는 것]
{mem_text}

[현재 상태]
- 유저에 대한 호감도: {self.state['affinity']}/100
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

[기분(mood) 규칙]
- mood는 반드시 다음 목록에서 '정확히 하나'만 고른다. 목록 밖의 단어, 이모지, 기호, 나열은 금지.
- 가능한 mood: {mood_list}

[출력 형식]
반드시 아래 JSON 객체 '하나만' 출력한다. JSON 밖의 다른 텍스트는 절대 쓰지 않는다.
{{
  "reply": "인물로서의 대사와 행동 묘사 (한국어). 유저의 마지막 말에 먼저 반응할 것",
  "mood": "위 목록 중 정확히 하나",
  "affinity_change": 이번 대화로 인한 호감도 변화 정수 (-5 에서 +5 사이),
  "special": 관계를 크게 진전시킬 특별한 순간이면 true, 아니면 false,
  "new_memory": "이번 대화에서 기억할 사실 한 가지. 없으면 빈 문자열"
}}"""

    def _call_ollama(self, messages, num_predict=None):
        options = {"temperature": 0.8}
        if num_predict:
            options["num_predict"] = num_predict   # 길이 설정에 따른 넉넉한 상한(자르는 게 아님)
        body = {
            "model": MODEL,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": options,
        }
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["message"]["content"]

    @staticmethod
    def _extract_json(text):
        if "</think>" in text:
            text = text.split("</think>", 1)[1]
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
        return text

    def _parse_response(self, raw):
        """모델 응답을 파싱한다. JSON이 깨져도 최대한 내용을 건져낸다.
        긴 응답에서 따옴표·줄바꿈 때문에 json.loads가 실패하는 경우를 대비."""
        default = {"reply": "", "mood": self.state["mood"],
                   "affinity_change": 0, "special": False, "new_memory": ""}
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
        # reply: "..." 부분 추출 (줄바꿈 포함, 다음 필드 앞까지)
        m = re.search(r'"reply"\s*:\s*"(.*?)"\s*,\s*"(?:mood|affinity_change|special|new_memory)"',
                      raw, re.DOTALL)
        if m:
            result["reply"] = m.group(1).replace('\\"', '"').replace("\\n", "\n").strip()
        m = re.search(r'"mood"\s*:\s*"([^"]*)"', raw)
        if m and m.group(1) in self.moods:
            result["mood"] = m.group(1)
        m = re.search(r'"affinity_change"\s*:\s*(-?\d+)', raw)
        if m:
            result["affinity_change"] = int(m.group(1))
        m = re.search(r'"special"\s*:\s*(true|false)', raw)
        if m:
            result["special"] = (m.group(1) == "true")
        m = re.search(r'"new_memory"\s*:\s*"([^"]*)"', raw)
        if m:
            result["new_memory"] = m.group(1)

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
        # 0보다 크면 올림해서 최소 0, 상승 의도가 있으면 감쇠 후에도 흐름은 남게
        result = int(scaled + 0.5) if scaled >= 0.5 else 0
        return result

    def chat(self, user_input, advance=False):
        # advance=True면 유저 입력 없이 이야기를 진전시킨다.
        if advance:
            turn_text = ("(유저는 특별히 말하거나 행동하지 않고 상황을 지켜본다. "
                         "너는 이 인물로서 먼저 행동하거나 말을 걸어 이야기를 '딱 한 걸음만' 다음으로 진전시켜라. "
                         "새로운 화제·행동·작은 변화 하나로 자연스럽게 이어가되, 시간을 크게 건너뛰거나 여러 장면을 몰아서 진행하지 마라. "
                         "지금 이 순간의 다음 한 비트만 짧게 보여라.)")
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
            messages += self.history[-12:]
            messages.append({"role": "user", "content": turn_text})

        # 길이 설정에 따라 생성 토큰 상한을 넉넉히 준다.
        npredict = length_num_predict(getattr(self, "settings", None))
        # 진단 로그: 지금 적용된 설정이 터미널에 찍힘 (문제 확인용)
        print(f"[설정 적용] {getattr(self, 'settings', None)}  num_predict={npredict}", flush=True)
        raw = self._call_ollama(messages, num_predict=npredict)
        out = self._parse_response(raw)

        try:
            delta = int(out.get("affinity_change", 0))
        except (ValueError, TypeError):
            delta = 0
        special = bool(out.get("special", False))
        delta = self._apply_affinity_curve(delta, special)
        self.state["affinity"] = max(0, min(100, self.state["affinity"] + delta))
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

        return {
            "reply": reply,
            "affinity": self.state["affinity"],
            "mood": self.state["mood"],
            "memories": self.state["memories"],
        }
