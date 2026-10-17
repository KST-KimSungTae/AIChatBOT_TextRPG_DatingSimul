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

# 캐릭터 기준 초상 이미지 폴더.
PORTRAIT_DIR = Path(__file__).parent.parent / "data" / "portraits"
PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)

# 갤러리(초상 확정 이후 생성된 사진들) 폴더.
GALLERY_DIR = Path(__file__).parent.parent / "data" / "gallery"
GALLERY_DIR.mkdir(parents=True, exist_ok=True)


def _path(char_id):
    return DATA_DIR / f"{char_id}.json"


# ── 초상(기준 이미지) ─────────────────────────────
def portrait_path(char_id):
    return PORTRAIT_DIR / f"{char_id}.png"


def has_portrait(char_id):
    return portrait_path(char_id).exists()


def portrait_mtime(char_id):
    p = portrait_path(char_id)
    return int(p.stat().st_mtime) if p.exists() else 0


def save_portrait(char_id, png_bytes):
    portrait_path(char_id).write_bytes(png_bytes)


# ── 갤러리 ────────────────────────────────────────
def gallery_dir(char_id):
    d = GALLERY_DIR / char_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_to_gallery(char_id, png_bytes, seed=0):
    """생성된 사진을 갤러리에 저장하고 파일명을 반환한다."""
    import time as _t
    fname = f"{int(_t.time() * 1000)}_{seed}.png"
    (gallery_dir(char_id) / fname).write_bytes(png_bytes)
    return fname


def list_gallery(char_id):
    """갤러리 파일명 목록(최신 먼저)."""
    d = GALLERY_DIR / char_id
    if not d.exists():
        return []
    files = sorted(d.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files]


def gallery_file(char_id, filename):
    """경로 우회 방지: 파일명만 허용."""
    if "/" in filename or "\\" in filename or ".." in filename:
        return None
    p = GALLERY_DIR / char_id / filename
    return p if p.exists() else None


def set_character_image(char_id, tags=None, seed=None):
    """이미지 태그·기준 시드를 캐릭터 파일에 캐시(Phase B 일관성 재사용용)."""
    data = get_character(char_id)
    if not data:
        return
    img = data.get("image") or {}
    if tags is not None:
        img["tags"] = tags
    if seed is not None:
        img["seed"] = seed
    data["image"] = img
    _path(char_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
    pp = portrait_path(char_id)
    if pp.exists():
        pp.unlink()          # 초상도 함께 삭제
    gd = GALLERY_DIR / char_id   # 갤러리도 함께 삭제
    if gd.exists():
        for f in gd.glob("*.png"):
            f.unlink()
        gd.rmdir()
    if p.exists():
        p.unlink()
        return True
    return False
