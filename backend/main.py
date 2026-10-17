# -*- coding: utf-8 -*-
"""
FastAPI 백엔드.
- 스키마 제공(폼 자동생성용), 캐릭터 CRUD, 캐릭터별 대화 세션.

주요 엔드포인트:
  GET  /api/schema           : 캐릭터/플레이어 설정 항목 정의
  GET  /api/characters       : 저장된 캐릭터 목록
  POST /api/characters       : 새 캐릭터 생성
  GET  /api/characters/{id}  : 캐릭터 상세
  DELETE /api/characters/{id}: 삭제
  POST /api/chat/{id}        : 그 캐릭터와 대화
  POST /api/chat/{id}/reset  : 그 캐릭터와의 대화 초기화

실행:
  cd backend
  pip install -r ../requirements.txt
  uvicorn main:app --reload
브라우저: http://localhost:8000
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import store
from schema import CHARACTER_SCHEMA, PLAYER_SCHEMA
from engine import ChatEngine
from settings_def import SETTINGS_DEF

app = FastAPI(title="Character Chatbot")

# 캐릭터별 대화 세션(엔진)을 메모리에 보관 → 캐릭터마다 호감도·기억이 분리됨
sessions = {}


def get_session(char_id):
    if char_id not in sessions:
        data = store.get_character(char_id)
        if not data:
            return None
        # 저장된 대화 진행 상태가 있으면 불러와 복원(없으면 새 대화로 시작)
        saved = store.load_session(char_id)
        sessions[char_id] = ChatEngine(
            data["character"], data.get("player"), saved_session=saved
        )
    return sessions[char_id]


# ── 스키마 ───────────────────────────────────────
@app.get("/api/schema")
def get_schema():
    return {"character": CHARACTER_SCHEMA, "player": PLAYER_SCHEMA}


# ── 캐릭터 CRUD ──────────────────────────────────
class CharacterPayload(BaseModel):
    character: dict
    player: dict = {}


@app.get("/api/characters")
def list_characters():
    return store.list_characters()


@app.post("/api/characters")
def create_character(payload: CharacterPayload):
    if not payload.character.get("name"):
        raise HTTPException(400, "이름은 필수야.")
    return store.create_character(payload.character, payload.player)


@app.get("/api/characters/{char_id}")
def get_character(char_id: str):
    data = store.get_character(char_id)
    if not data:
        raise HTTPException(404, "캐릭터를 찾을 수 없어.")
    return data


@app.delete("/api/characters/{char_id}")
def delete_character(char_id: str):
    sessions.pop(char_id, None)
    if not store.delete_character(char_id):
        raise HTTPException(404, "캐릭터를 찾을 수 없어.")
    return {"ok": True}


# ── 대화 ─────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat/{char_id}")
def chat(char_id: str, req: ChatRequest):
    engine = get_session(char_id)
    if not engine:
        raise HTTPException(404, "캐릭터를 찾을 수 없어.")
    result = engine.chat(req.message)
    store.save_session(char_id, engine.export_session())   # 매 턴 저장
    return result


@app.post("/api/chat/{char_id}/advance")
def chat_advance(char_id: str):
    """유저 입력 없이 이야기를 다음으로 진전시킨다('진행하기')."""
    engine = get_session(char_id)
    if not engine:
        raise HTTPException(404, "캐릭터를 찾을 수 없어.")
    result = engine.chat("", advance=True)
    store.save_session(char_id, engine.export_session())
    return result


@app.post("/api/chat/{char_id}/suggest")
def chat_suggest(char_id: str):
    """유저가 할 만한 대사를 하나 제안한다(자동 대사 버튼). 상태는 바꾸지 않는다."""
    engine = get_session(char_id)
    if not engine:
        raise HTTPException(404, "캐릭터를 찾을 수 없어.")
    return {"line": engine.suggest_user_line()}


@app.get("/api/chat/{char_id}/state")
def chat_state(char_id: str):
    engine = get_session(char_id)
    if not engine:
        raise HTTPException(404, "캐릭터를 찾을 수 없어.")
    return {
        "affinity": engine.state["affinity"],
        "trust": engine.state.get("trust", 0),
        "mood": engine.state["mood"],
        "memories": engine.state["memories"],
        "history": engine.history,          # 뒤로 갔다 와도 대화 복원되도록
        "settings": engine.settings,        # 현재 대화 설정(슬라이더 값)
        "unlock": engine.public_unlock(),   # 힌트(가림)·해방 여부
        "character": engine.char,
    }


@app.get("/api/settings-def")
def settings_def():
    """슬라이더 정의(프론트가 설정 패널을 자동 생성)."""
    return SETTINGS_DEF


class SettingsPayload(BaseModel):
    settings: dict


@app.post("/api/chat/{char_id}/settings")
def update_settings(char_id: str, payload: SettingsPayload):
    engine = get_session(char_id)
    if not engine:
        raise HTTPException(404, "캐릭터를 찾을 수 없어.")
    engine.update_settings(payload.settings)
    store.save_session(char_id, engine.export_session())
    return {"settings": engine.settings}


@app.post("/api/chat/{char_id}/reset")
def chat_reset(char_id: str):
    data = store.get_character(char_id)
    if not data:
        raise HTTPException(404, "캐릭터를 찾을 수 없어.")
    store.clear_session(char_id)            # 저장된 진행 상태도 삭제
    sessions[char_id] = ChatEngine(data["character"], data.get("player"))
    return {"ok": True}


# 프론트엔드 정적 파일 서빙 (API 라우트들 뒤에 둔다)
frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
