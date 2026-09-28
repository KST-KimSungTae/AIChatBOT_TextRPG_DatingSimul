# -*- coding: utf-8 -*-
"""
설정 항목 스키마.

캐릭터/플레이어 폼을 하드코딩하지 않고 이 정의에서 '자동 생성'한다.
→ 나중에 항목을 추가하려면 여기에 한 항목만 더 넣으면 폼·저장이 모두 따라온다.

각 필드:
  key       : 저장/전송에 쓰는 식별자
  label     : 화면에 보일 이름
  type      : "text" | "textarea" | "number" | "select" | "list" | "tags"
  required  : 필수 여부
  hint      : 입력 도움말(placeholder)
  options   : select일 때 선택지
  default   : 기본값
  group     : 폼에서 묶을 섹션
"""

# ── 캐릭터 설정 항목 ─────────────────────────────
CHARACTER_SCHEMA = [
    # 기본
    {"key": "name", "label": "이름", "type": "text", "required": True,
     "hint": "캐릭터 이름", "group": "기본"},
    {"key": "age_range", "label": "나이대", "type": "text", "required": False,
     "hint": "예: 20대 초반", "group": "기본"},
    {"key": "type", "label": "성별/유형", "type": "text", "required": False,
     "hint": "예: 미소녀", "default": "미소녀", "group": "기본"},
    {"key": "tagline", "label": "한 줄 소개", "type": "text", "required": False,
     "hint": "캐릭터를 한 문장으로", "group": "기본"},

    # 성격·말투
    {"key": "personality", "label": "성격", "type": "textarea", "required": True,
     "hint": "내면 성향, 태도", "group": "성격·말투"},
    {"key": "speech_style", "label": "말투", "type": "textarea", "required": True,
     "hint": "반말/존댓말, 톤, 특징", "group": "성격·말투"},
    {"key": "voice_examples", "label": "말투 예시", "type": "list", "required": False,
     "hint": "이 캐릭터라면 할 법한 대사 몇 개 (어투를 잡는 핵심)", "group": "성격·말투"},
    {"key": "address_term", "label": "유저를 부르는 호칭", "type": "text", "required": False,
     "hint": "예: 이름, 너, 당신, 주인님", "default": "너", "group": "성격·말투"},

    # 배경·세계관
    {"key": "background", "label": "배경/재력", "type": "textarea", "required": False,
     "hint": "신분, 재산, 처지", "group": "배경·세계관"},
    {"key": "world", "label": "세계관", "type": "textarea", "required": False,
     "hint": "예: 현대, 판타지, 학원물", "group": "배경·세계관"},
    {"key": "scene", "label": "초기 장면", "type": "textarea", "required": True,
     "hint": "첫 대화가 시작되는 상황", "group": "배경·세계관"},

    # 관계
    {"key": "relationship", "label": "유저와의 관계", "type": "text", "required": False,
     "hint": "예: 낯선 사람, 친구, 연인, 주종, 소꿉친구",
     "default": "낯선 사람", "group": "관계"},
    {"key": "initial_affinity", "label": "초기 호감도", "type": "number", "required": False,
     "hint": "0~100 (연인이면 높게, 낯선 사람이면 낮게)",
     "default": 30, "group": "관계"},

    # 외모 (지금은 텍스트만, 나중에 이미지 생성에 사용)
    {"key": "appearance", "label": "외모 묘사", "type": "textarea", "required": False,
     "hint": "머리·눈·체형 등 (나중에 이미지 생성에 쓰임)", "group": "외모"},
    {"key": "outfit", "label": "자주 입는 옷/컬러", "type": "textarea", "required": False,
     "hint": "복장, 색 (나중에 이미지 생성에 쓰임)", "group": "외모"},

    # 기분 목록 (캐릭터별 커스텀, 기본 세트 제공)
    {"key": "moods", "label": "기분 목록", "type": "tags", "required": False,
     "hint": "이 캐릭터가 가질 수 있는 감정들",
     "default": ["경계", "무관심", "냉담", "짜증", "불쾌",
                 "차분", "호기심", "흥미", "누그러짐", "다정",
                 "쓸쓸", "그리움", "슬픔", "당황", "설렘"],
     "group": "기분"},
]

# ── 플레이어 페르소나 항목 ───────────────────────
PLAYER_SCHEMA = [
    {"key": "name", "label": "이름", "type": "text", "required": False,
     "hint": "캐릭터가 나를 부를 이름", "group": "플레이어"},
    {"key": "gender", "label": "성별", "type": "text", "required": False,
     "hint": "예: 남성, 여성", "group": "플레이어"},
    {"key": "age_range", "label": "나이대", "type": "text", "required": False,
     "hint": "예: 20대", "group": "플레이어"},
    {"key": "background", "label": "배경/설정", "type": "textarea", "required": False,
     "hint": "예: 떠돌이 용병, 옆집에 이사 온 사람", "group": "플레이어"},
    {"key": "appearance", "label": "외모", "type": "textarea", "required": False,
     "hint": "선택 — 나중에 필요할 수 있음", "group": "플레이어"},
]


def default_from_schema(schema):
    """스키마의 default 값으로 빈 설정 dict를 만든다."""
    out = {}
    for field in schema:
        if field["type"] == "list":
            out[field["key"]] = field.get("default", [])
        elif field["type"] == "tags":
            out[field["key"]] = list(field.get("default", []))
        else:
            out[field["key"]] = field.get("default", "")
    return out
