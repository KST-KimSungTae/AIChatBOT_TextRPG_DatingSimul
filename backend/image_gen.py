# -*- coding: utf-8 -*-
"""
ComfyUI 이미지 생성 클라이언트 (Phase A).
검증된 txt2img 워크플로우로 NoobAI 이미지를 생성해 PNG 바이트로 돌려준다.

comfy_test.py로 배관을 확인한 그 경로를 모듈로 정리한 것.
설정은 아래 CONFIG에서 네 ComfyUI 환경에 맞춘다.
"""

import json
import time
import uuid
import urllib.request
import urllib.parse

# ── CONFIG (네 ComfyUI 환경에 맞게) ─────────────────────
COMFYUI_URL = "http://127.0.0.1:8188"
CKPT_NAME = "noobaiXLNAIXL_epsilonPred11Version.safetensors"   # 체크포인트 파일명
VAE_NAME = "sdxl-vae-fp16-fix.safetensors"   # 외부 VAE(네 워크플로우와 동일). 비우면 내장 VAE.
CLIP_SKIP = -2             # 애니 SDXL 표준
WIDTH, HEIGHT = 1024, 1536  # 네 워크플로우와 동일(세로 2:3)
STEPS = 20
CFG = 8.0
SAMPLER = "euler"
SCHEDULER = "simple"

# 품질 태그 접두 / 기본 네거티브
QUALITY_PREFIX = "masterpiece, best quality, newest, absurdres, highres, "
DEFAULT_NEGATIVE = ("worst quality, low quality, bad anatomy, bad hands, missing fingers, "
                    "extra digits, fewer digits, watermark, signature, text, "
                    "jpeg artifacts, blurry, lowres")
# ────────────────────────────────────────────────────────


def _build_workflow(positive, negative, seed):
    wf = {
        "ckpt": {"class_type": "CheckpointLoaderSimple",
                 "inputs": {"ckpt_name": CKPT_NAME}},
        "clipskip": {"class_type": "CLIPSetLastLayer",
                     "inputs": {"clip": ["ckpt", 1], "stop_at_clip_layer": CLIP_SKIP}},
        "pos": {"class_type": "CLIPTextEncode",
                "inputs": {"text": QUALITY_PREFIX + positive, "clip": ["clipskip", 0]}},
        "neg": {"class_type": "CLIPTextEncode",
                "inputs": {"text": negative or DEFAULT_NEGATIVE, "clip": ["clipskip", 0]}},
        "latent": {"class_type": "EmptyLatentImage",
                   "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": 1}},
        "sampler": {"class_type": "KSampler",
                    "inputs": {"seed": seed, "steps": STEPS, "cfg": CFG,
                               "sampler_name": SAMPLER, "scheduler": SCHEDULER,
                               "denoise": 1.0, "model": ["ckpt", 0],
                               "positive": ["pos", 0], "negative": ["neg", 0],
                               "latent_image": ["latent", 0]}},
        "decode": {"class_type": "VAEDecode",
                   "inputs": {"samples": ["sampler", 0]}},
        "save": {"class_type": "SaveImage",
                 "inputs": {"images": ["decode", 0], "filename_prefix": "chatbot"}},
    }
    # VAE: 외부 VAE 지정 시 VAELoader 사용, 아니면 체크포인트 내장
    if VAE_NAME:
        wf["vaeload"] = {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}}
        wf["decode"]["inputs"]["vae"] = ["vaeload", 0]
    else:
        wf["decode"]["inputs"]["vae"] = ["ckpt", 2]
    return wf


def _post(path, payload):
    req = urllib.request.Request(
        COMFYUI_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path):
    with urllib.request.urlopen(COMFYUI_URL + path, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_image(info):
    q = urllib.parse.urlencode({
        "filename": info["filename"],
        "subfolder": info.get("subfolder", ""),
        "type": info.get("type", "output"),
    })
    with urllib.request.urlopen(f"{COMFYUI_URL}/view?{q}", timeout=30) as resp:
        return resp.read()


def free_comfy():
    """ComfyUI에게 VRAM에 올린 모델을 내리라고 요청한다(best-effort).

    12GB VRAM에서 LLM과 SDXL이 공존할 수 없으므로, 이미지 생성이 끝나면
    SDXL을 내려서 다음 LLM 호출(캐릭터 생성·대화)이 GPU로 돌아가게 한다.
    (unload_llm()의 짝. 실패해도 생성 결과엔 영향 없으니 조용히 넘어간다.)
    """
    try:
        _post("/free", {"unload_models": True, "free_memory": True})
        print("[image_gen] ComfyUI VRAM 해제 요청 완료", flush=True)
    except Exception as e:
        print("[image_gen] VRAM 해제 요청 실패(무시):", repr(e), flush=True)


def generate_one(positive, negative="", seed=None, timeout_s=120, free_after=False):
    """이미지 1장 생성 → PNG bytes. 실패 시 None.
    free_after=True면 생성 후 ComfyUI VRAM을 내린다(단발 생성용. 배치는 False)."""
    if seed is None:
        seed = uuid.uuid4().int % (2 ** 31)
    client_id = uuid.uuid4().hex
    try:
        res = _post("/prompt", {"prompt": _build_workflow(positive, negative, seed),
                                "client_id": client_id})
    except Exception as e:
        print("[image_gen] 제출 실패:", repr(e), flush=True)
        return None
    prompt_id = res.get("prompt_id")
    if not prompt_id:
        print("[image_gen] prompt_id 없음:", res, flush=True)
        return None

    png = None
    done = False
    for _ in range(timeout_s):
        time.sleep(1)
        try:
            hist = _get(f"/history/{prompt_id}")
        except Exception:
            continue
        if prompt_id in hist:
            for node_out in hist[prompt_id].get("outputs", {}).values():
                imgs = node_out.get("images", [])
                if imgs:
                    try:
                        png = _fetch_image(imgs[0])
                    except Exception as e:
                        print("[image_gen] 이미지 수신 실패:", repr(e), flush=True)
                        png = None
                    done = True
                    break
            if done:
                break
    if not done:
        print("[image_gen] 시간 초과", flush=True)

    if free_after:
        free_comfy()
    return png


def generate_variations(positive, negative="", n=4):
    """시드를 다르게 n장 생성 → [(seed, png_bytes), ...]. 실패한 건 건너뜀.
    배치가 끝나면 VRAM을 한 번만 내린다(매 장마다 내렸다 올리는 낭비 방지)."""
    out = []
    for _ in range(n):
        seed = uuid.uuid4().int % (2 ** 31)
        png = generate_one(positive, negative, seed=seed, free_after=False)
        if png:
            out.append((seed, png))
    free_comfy()   # 배치 종료 후 SDXL을 내려 다음 LLM 호출에 VRAM 양보
    return out


def ping():
    """ComfyUI가 응답하는지 확인."""
    try:
        _get("/system_stats")
        return True
    except Exception:
        return False
