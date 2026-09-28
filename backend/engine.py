# -*- coding: utf-8 -*-
"""
대화 엔진. 이제 특정 캐릭터에 고정되지 않고, 어떤 캐릭터/플레이어 설정이든 받아서 동작한다.
- 캐릭터 dict + 플레이어 dict로 페르소나 프롬프트를 조립
- Ollama(Gemma) 호출, 호감도/기분/기억 상태 관리
캐릭터별로 ChatEngine 인스턴스를 하나씩 두면 세션이 분리된다(main.py가 관리).
"""

import json
import urllib.request

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
            return

        # 저장된 게 없으면(새 대화) 초기 상태를 세팅한다.
        try:
            start = int(character.get("initial_affinity", 30))
        except (ValueError, TypeError):
            start = 30
        start = max(0, min(100, start))

        # 초기 기분: 캐릭터에 이미 저장돼 있으면(생성 시 계산됨) 그대로 읽어 즉시 시작한다.
        saved = character.get("initial_state") or {}
        saved_mood = saved.get("mood")
        self.state = {
            "affinity": start,
            "mood": saved_mood if saved_mood in self.moods else None,
            "memories": [],
        }
        self.history = []
        if self.state["mood"] is None:
            self.state["mood"] = self._decide_initial_mood()

    def export_session(self):
        """현재 진행 상태를 저장용 dict로 반환."""
        return {
            "affinity": self.state["affinity"],
            "mood": self.state["mood"],
            "memories": self.state["memories"],
            "history": self.history,
        }

    @classmethod
    def scan_initial_state(cls, character, player=None):
        """캐릭터 '생성 시점'에 딱 한 번 호출. AI로 초기 기분을 계산해 dict로 돌려준다.
        이 결과를 캐릭터 JSON의 'initial_state'에 저장해두면, 이후 진입 때는 계산 없이 즉시 로드된다."""
        engine = cls.__new__(cls)          # __init__을 우회해 계산용으로만 생성
        engine.char = character
        engine.player = player or {}
        engine.moods = character.get("moods") or DEFAULT_MOODS
        try:
            aff = int(character.get("initial_affinity", 30))
        except (ValueError, TypeError):
            aff = 30
        engine.state = {"affinity": max(0, min(100, aff))}
        mood = engine._decide_initial_mood()
        return {"mood": mood}

    def _decide_initial_mood(self):
        """AI에게 '이 캐릭터가 이 상황에서 지금 어떤 기분인지'를 판단시켜 초기 기분을 정한다.
        성격·배경·초기 장면·관계·호감도를 근거로 기분 목록 중 하나를 고르게 한다.
        실패하면 안전하게 목록 중간값으로 폴백."""
        c = self.char
        mood_list = ", ".join(self.moods)
        rel = c.get("relationship", "")
        prompt = f"""다음 인물이 '이야기가 시작되는 지금 이 순간' 어떤 기분일지 하나만 판단해라.

[인물] {c.get('name','')}
- 성격: {c.get('personality','')}
- 배경: {c.get('background','')}
- 유저와의 관계: {rel}
- 유저에 대한 호감도: {self.state['affinity']}/100
- 지금 장면: {c.get('scene','')}

이 상황과 감정을 종합해서, 아래 목록 중 지금 기분에 가장 맞는 것 '하나'만 고른다.
가능한 기분: {mood_list}

반드시 아래 JSON 형식으로만 답한다.
{{"mood": "목록 중 하나"}}"""
        try:
            raw = self._call_ollama([{"role": "user", "content": prompt}])
            data = json.loads(self._extract_json(raw))
            mood = (data.get("mood") or "").strip()
            if mood in self.moods:
                return mood
        except Exception:
            pass
        # 폴백: 목록 중간값
        return self.moods[len(self.moods) // 2] if self.moods else "차분"

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
- reply는 반드시 유저의 '마지막 말'에 직접 반응하는 내용으로 시작한다. 방금 한 말을 무시하고 설정이나 배경을 혼자 읊지 않는다.
- 유저 입력에서 괄호 '( )' 안은 유저의 '행동·상황' 묘사이고, 괄호 밖은 유저의 '대사'다. 둘 다 고려해 반응하되, 행동은 행동으로 대사는 대사로 이해한다. (예: (다가와 머리를 쓰다듬으며) 잘했어 → 유저가 머리를 쓰다듬으면서 칭찬한 것)

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

    def _call_ollama(self, messages):
        body = {
            "model": MODEL,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.8},
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

    def chat(self, user_input):
        # Gemma 대응: system 롤 없이 페르소나를 user 메시지로 전달
        messages = []
        if not self.history:
            merged = self.build_system_prompt() + "\n\n---\n\n[유저] " + user_input
            messages.append({"role": "user", "content": merged})
        else:
            messages.append({"role": "user", "content": self.build_system_prompt()})
            messages.append({"role": "assistant", "content": "알겠어. 이 인물로서 대화를 이어갈게."})
            messages += self.history[-12:]
            messages.append({"role": "user", "content": user_input})

        raw = self._call_ollama(messages)
        try:
            out = json.loads(self._extract_json(raw))
        except json.JSONDecodeError:
            out = {"reply": raw, "mood": self.state["mood"],
                   "affinity_change": 0, "new_memory": ""}

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
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": reply})

        return {
            "reply": reply,
            "affinity": self.state["affinity"],
            "mood": self.state["mood"],
            "memories": self.state["memories"],
        }
