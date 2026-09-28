# -*- coding: utf-8 -*-
"""
캐릭터 저장소. 캐릭터 하나 = JSON 파일 하나.
data/characters/ 폴더에 저장하고, 목록·생성·조회·삭제를 제공한다.
"""

import json
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "characters"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 대화 진행 상태(호감도·기분·기억·대화기록)를 저장하는 폴더. 캐릭터 설정과 분리.
SESSION_DIR = Path(__file__).parent.parent / "data" / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _path(char_id):
    return DATA_DIR / f"{char_id}.json"


def _session_path(char_id):
    return SESSION_DIR / f"{char_id}.json"


def load_session(char_id):
    """저장된 대화 진행 상태를 불러온다. 없으면 None."""
    p = _session_path(char_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_session(char_id, session):
    """대화 진행 상태를 저장한다. session = {affinity, mood, memories, history}."""
    _session_path(char_id).write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def clear_session(char_id):
    """대화 진행 상태를 지운다('처음부터' 또는 캐릭터 삭제 시)."""
    p = _session_path(char_id)
    if p.exists():
        p.unlink()


def list_characters():
    """저장된 캐릭터들의 요약 목록."""
    result = []
    for f in sorted(DATA_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            result.append({
                "id": data.get("id"),
                "name": data.get("character", {}).get("name", "이름 없음"),
                "tagline": data.get("character", {}).get("tagline", ""),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return result


def get_character(char_id):
    p = _path(char_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def create_character(character, player):
    """새 캐릭터 저장. 생성 시점에 딱 한 번 AI로 초기 상태(기분)를 스캔해 함께 저장한다.
    → 이후 대화 진입 때는 이 저장값을 즉시 읽어 딜레이가 없다."""
    from engine import ChatEngine   # 순환 import 방지를 위해 함수 안에서 import
    char_id = uuid.uuid4().hex[:12]
    initial_state = ChatEngine.scan_initial_state(character, player)
    character = {**character, "initial_state": initial_state}
    data = {"id": char_id, "character": character, "player": player}
    _path(char_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def update_character(char_id, character, player):
    data = get_character(char_id)
    if not data:
        return None
    data["character"] = character
    data["player"] = player
    _path(char_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def delete_character(char_id):
    p = _path(char_id)
    clear_session(char_id)   # 대화 진행 상태도 함께 삭제
    if p.exists():
        p.unlink()
        return True
    return False
