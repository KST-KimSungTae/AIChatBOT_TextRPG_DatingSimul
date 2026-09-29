# -*- coding: utf-8 -*-
"""
대화 설정(슬라이더) 정의. 나중에 슬라이더를 더하거나 빼려면 여기만 고치면 된다.

각 설정:
  key      : 저장/전송 식별자
  label    : 화면에 보일 이름
  min/max  : 슬라이더 단계 범위
  default  : 기본값(지금 동작 = 중간값 3)
  low_label / high_label : 슬라이더 양끝 설명
  prompts  : 단계값 → 프롬프트에 들어갈 문장 (1~5). 추상어 대신 '구체적 지시'로 써야
             12B 모델이 확실히 따른다.
"""

SETTINGS_DEF = [
    {
        "key": "pace",
        "label": "진행 속도",
        "min": 1, "max": 5, "default": 3,
        "low_label": "천천히", "high_label": "빠르게",
        "prompts": {
            1: "진행 속도: 매우 느리게. 지금 이 순간에 오래 머무른다. 장면을 다음으로 넘기지 말고, 사소한 감정과 디테일만 길게 음미한다.",
            2: "진행 속도: 느리게. 장면을 서두르지 않고, 한 상황을 충분히 곱씹은 뒤에만 아주 조금 나아간다.",
            3: "진행 속도: 보통. 자연스러운 속도로 이야기를 이어간다.",
            4: "진행 속도: 빠르게. 한 응답마다 이야기를 눈에 띄게 다음 단계로 넘긴다. 같은 상황에 머무르지 말고 새 전개(이동·사건·화제 전환)를 만든다.",
            5: "진행 속도: 매우 빠르게. 반드시 매 응답마다 장면을 실제로 다음 단계로 진행시킨다. 멈춰서 풍경이나 감정을 감상만 하지 말고, 구체적인 행동·이동·사건으로 이야기를 적극 전진시킨다. 정체는 금지.",
        },
    },
    {
        "key": "proactivity",
        "label": "능동성",
        "min": 1, "max": 5, "default": 3,
        "low_label": "수동적", "high_label": "능동적",
        "prompts": {
            1: "능동성: 매우 수동적. 유저의 말과 행동에 반응만 한다. 먼저 나서지 않고, 유저가 이끄는 대로 따라간다.",
            2: "능동성: 수동적. 주로 반응하되, 가끔만 스스로 화제를 꺼낸다.",
            3: "능동성: 보통. 반응하면서도 매번 허락을 구하지 않고 스스로 다음 행동을 한다.",
            4: "능동성: 능동적. 유저의 동의를 기다리지 않는다. 스스로 결정하고 행동하며 이야기를 이끈다. '~할까?', '그치?' 같은 되묻는 말을 되도록 쓰지 않는다.",
            5: "능동성: 매우 능동적. 절대 유저에게 되묻거나 허락을 구하지 않는다. '~할까?', '~어때?', '그치?', '알았지?' 같이 유저 대답을 기다리는 문장을 쓰지 마라. 인물이 스스로 결정하고 먼저 행동하며 장면을 만들어 나간다. 유저는 그 흐름에 반응할 뿐이다.",
        },
    },
    {
        "key": "length",
        "label": "응답 길이",
        "min": 1, "max": 5, "default": 3,
        "low_label": "짧게", "high_label": "길게",
        "prompts": {
            1: "응답 길이: 아주 짧게. reply는 1~2문장. 군더더기 없이 핵심만.",
            2: "응답 길이: 짧게. reply는 2~3문장.",
            3: "응답 길이: 보통. reply는 3~4문장.",
            4: "응답 길이: 길게. reply는 최소 5문장 이상. 대사뿐 아니라 표정·몸짓·행동 묘사를 곳곳에 넣어 장면을 생생하게 그린다.",
            5: "응답 길이: 매우 길게. reply는 반드시 6문장 이상으로 충분히 길게 쓴다. 대사 사이사이에 표정·몸짓·행동·주변 묘사를 풍부하게 섞어, 한 편의 소설 장면처럼 생생하고 자세하게 서술한다. 짧게 끝내지 마라.",
        },
    },
]


def default_settings():
    return {s["key"]: s["default"] for s in SETTINGS_DEF}


def settings_to_prompt(settings):
    """설정값(dict)을 프롬프트 문장들로 변환."""
    settings = settings or {}
    lines = []
    for s in SETTINGS_DEF:
        val = settings.get(s["key"], s["default"])
        try:
            val = int(val)
        except (ValueError, TypeError):
            val = s["default"]
        val = max(s["min"], min(s["max"], val))
        line = s["prompts"].get(val)
        if line:
            lines.append(f"- {line}")
    return "\n".join(lines)


def length_num_predict(settings):
    """응답 길이 설정에 따라 생성 토큰 상한을 넉넉히 준다.
    (자르는 하한이 아니라, 길게 쓸 '공간'을 주는 상한. None이면 무제한.)"""
    settings = settings or {}
    try:
        val = int(settings.get("length", 3))
    except (ValueError, TypeError):
        val = 3
    # 값이 낮을수록 상한을 낮춰 짧게, 높을수록 넉넉히. 너무 낮게는 안 줘서 JSON이 안 잘리게.
    return {1: 400, 2: 550, 3: 800, 4: 1200, 5: 1800}.get(val, 800)
