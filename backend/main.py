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

import base64
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import store
import image_gen
import engine as engine_mod
from schema import CHARACTER_SCHEMA, PLAYER_SCHEMA
from engine import ChatEngine
from settings_def import SETTINGS_DEF

app = FastAPI(title="Character Chatbot")

# 캐릭터별 대화 세션(엔진)을 메모리에 보관 → 캐릭터마다 호감도·기억이 분리됨
sessions = {}

# 초상 후보 임시 보관(선택 전까지): {char_id: [(seed, png_bytes), ...]}
portrait_candidates = {}


def get_session(char_id):
    if char_id not in sessions:
        data = store.get_character(char_id)
        if not data:
            return None
        # 저장된 대화 진행 상태가 있으면 불러와 복원(없으면 새 대화로 시작)
        saved = store.load_session(char_id)
        sessions[char_id] = ChatEngine(
            data["character"], data.get("player"), saved_session=saved,
            image=data.get("image"),
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
    # 갤러리(최신 먼저) = [장면들..., 기준 초상]. 장면이 있으면 최신 장면을 재입장 시 복원 표시.
    gallery = store.list_gallery(char_id)
    scene_url = (f"/api/characters/{char_id}/gallery/{gallery[0]}"
                 if len(gallery) > 1 else None)
    return {
        "affinity": engine.state["affinity"],
        "trust": engine.state.get("trust", 0),
        "mood": engine.state["mood"],
        "memories": engine.state["memories"],
        "history": engine.history,          # 뒤로 갔다 와도 대화 복원되도록
        "settings": engine.settings,        # 현재 대화 설정(슬라이더 값)
        "unlock": engine.public_unlock(),   # 힌트(가림)·해방 여부
        "portrait": (f"/api/characters/{char_id}/portrait?t={store.portrait_mtime(char_id)}"
                     if store.has_portrait(char_id) else None),
        "scene": scene_url,                 # 마지막 장면 이미지(없으면 None → 기준 초상 표시)
        "character": engine.char,
    }


# ── 초상(기준 이미지) 생성·선택·조회 ─────────────────
@app.post("/api/characters/{char_id}/portrait/variations")
def portrait_variations(char_id: str, n: int = 4, refresh_tags: int = 0):
    """시드 다른 후보 n장을 생성해 base64로 돌려준다. (첫 초상을 고르는 용도. 확정 후엔 호출 불가.)

    refresh_tags=0 : 저장된 태그 재사용(시드만 다르게) → LLM 호출 없음(빠름).
    refresh_tags=1 : 외모·의상을 LLM으로 다시 변환해 태그를 새로 뽑는다(느림).
                     (태그가 아직 없으면 refresh 값과 무관하게 한 번 변환한다.)
    """
    if not image_gen.ping():
        raise HTTPException(503, "ComfyUI에 연결할 수 없어. ComfyUI가 켜져 있는지 확인해줘.")
    data = store.get_character(char_id)
    if not data:
        raise HTTPException(404, "캐릭터를 찾을 수 없어.")
    if store.has_portrait(char_id):
        raise HTTPException(400, "이미 기준 초상이 확정됐어. 초상은 바꿀 수 없어.")

    engine = get_session(char_id)
    adult = bool(engine.settings.get("adult_images", False))   # 성인 이미지 허용 여부(기본 False)

    img = data.get("image") or {}
    body = img.get("body")
    base_outfit = img.get("base_outfit")
    # 태그가 없거나 '새로 뽑기'를 요청했을 때만 LLM 호출. 그 외엔 캐시 재사용(LLM 0회).
    if refresh_tags or not body:
        res = engine.appearance_to_tags()
        body, base_outfit = res["body"], res["base_outfit"]
        store.set_character_image(char_id, body=body, base_outfit=base_outfit)

    # 기준 초상 = 신체 + 중립 평상복. (선호 노출 의상은 초상에 넣지 않는다 → 장면 이미지에서만 등장)
    positive = ", ".join(t for t in [body, base_outfit] if t)
    negative = image_gen.build_negative(adult=adult)   # adult Off면 성인 가드 태그 추가

    # 이미지 뽑기 전에 LLM을 내려 VRAM 확보(12GB)
    engine_mod.unload_llm()

    n = max(1, min(6, int(n)))
    variants = image_gen.generate_variations(positive, negative=negative, n=n)
    if not variants:
        raise HTTPException(500, "이미지 생성에 실패했어. ComfyUI 콘솔의 에러를 확인해줘.")

    # 첫 초상 후보들은 갤러리에 저장하지 않는다(고르는 선택지일 뿐).
    portrait_candidates[char_id] = variants
    return {
        "body": body,
        "base_outfit": base_outfit,
        "candidates": [
            {"index": i, "seed": seed,
             "image": "data:image/png;base64," + base64.b64encode(png).decode()}
            for i, (seed, png) in enumerate(variants)
        ],
    }


class PortraitSelect(BaseModel):
    index: int


@app.post("/api/characters/{char_id}/portrait/select")
def portrait_select(char_id: str, payload: PortraitSelect):
    """후보 중 하나를 골라 기준 초상으로 확정 저장한다."""
    cands = portrait_candidates.get(char_id)
    if not cands:
        raise HTTPException(400, "먼저 후보를 생성해줘.")
    if not (0 <= payload.index < len(cands)):
        raise HTTPException(400, "잘못된 선택.")
    seed, png = cands[payload.index]
    store.save_portrait(char_id, png)
    store.save_to_gallery(char_id, png, seed)   # 확정 초상이 갤러리의 첫 사진
    store.set_character_image(char_id, seed=seed)
    portrait_candidates.pop(char_id, None)   # 임시 후보 정리
    return {"ok": True}


@app.get("/api/characters/{char_id}/portrait")
def portrait_get(char_id: str):
    if not store.has_portrait(char_id):
        raise HTTPException(404, "초상이 아직 없어.")
    return FileResponse(str(store.portrait_path(char_id)), media_type="image/png")


# ── 갤러리 ────────────────────────────────────────
@app.get("/api/characters/{char_id}/gallery")
def gallery_list(char_id: str):
    names = store.list_gallery(char_id)
    return {"images": [f"/api/characters/{char_id}/gallery/{n}" for n in names]}


@app.get("/api/characters/{char_id}/gallery/{filename}")
def gallery_image(char_id: str, filename: str):
    p = store.gallery_file(char_id, filename)
    if not p:
        raise HTTPException(404, "이미지를 찾을 수 없어.")
    return FileResponse(str(p), media_type="image/png")


# ── 장면 이미지 (Phase B: 대화 장면에 맞춘 이미지) ──────
class SceneImageRequest(BaseModel):
    image_prompt: str = ""


@app.post("/api/characters/{char_id}/scene-image")
def scene_image(char_id: str, req: SceneImageRequest):
    """확정 초상을 기준으로, 현재 장면 태그(image_prompt)를 얹어 장면 이미지를 생성한다.
    일관성: 같은 body(고정 외형) 태그 + 확정 초상의 '고정 시드' 재사용. 결과는 갤러리에 저장."""
    if not image_gen.ping():
        raise HTTPException(503, "ComfyUI에 연결할 수 없어. ComfyUI가 켜져 있는지 확인해줘.")
    data = store.get_character(char_id)
    if not data:
        raise HTTPException(404, "캐릭터를 찾을 수 없어.")
    if not store.has_portrait(char_id):
        raise HTTPException(400, "먼저 기준 초상을 확정해줘.")

    img = data.get("image") or {}
    body = img.get("body") or img.get("tags") or ""   # 신체 태그(구버전 캐시는 tags로 폴백)
    seed = img.get("seed")                       # 확정 초상의 시드 = 캐릭터 고정 시드
    scene = (req.image_prompt or "").strip()
    positive = ", ".join(t for t in [body, scene] if t)
    if not positive:
        raise HTTPException(400, "생성할 장면 정보가 없어.")

    engine = get_session(char_id)
    adult = bool(engine.settings.get("adult_images", False))
    negative = image_gen.build_negative(adult=adult)

    engine_mod.unload_llm()                       # VRAM 확보
    png = image_gen.generate_one(positive, negative=negative, seed=seed, free_after=True)
    if not png:
        raise HTTPException(500, "장면 이미지 생성에 실패했어. ComfyUI 콘솔을 확인해줘.")

    fname = store.save_to_gallery(char_id, png, seed or 0)
    return {"image": f"/api/characters/{char_id}/gallery/{fname}", "prompt": positive}


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
    sessions[char_id] = ChatEngine(data["character"], data.get("player"),
                                   image=data.get("image"))
    return {"ok": True}


# 프론트엔드 정적 파일 서빙 (API 라우트들 뒤에 둔다)
from paths import FRONTEND_DIR   # 개발/패키징(.exe) 환경에 맞는 프론트엔드 경로
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
