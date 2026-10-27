# 캐릭터 챗 — 로컬 캐릭터 AI 챗봇

외부 서버·과금·검열에 의존하지 않고, **단일 GPU(12GB) 로컬 환경**에서 LLM 대화와 실시간 이미지 생성을
결합한 몰입형 캐릭터 롤플레이 엔진입니다. (FastAPI 백엔드 + 무프레임워크 프론트엔드)

- 캐릭터 생성(성격·말투·배경·초기 장면·외모) → 대화
- 호감도·신뢰도 기반 관계 시뮬레이션, 기분·장기 기억
- 기준 초상 생성 + 장면마다 바뀌는 캐릭터 일관성 이미지 (ComfyUI)
- 성인 콘텐츠 수위는 **사용자 토글(기본 SFW)**로 제어

> 로컬·단일 사용자용. 캐릭터는 성인(20세+) 전제이며, 생성 이미지는 외부로 배포되지 않습니다.

---

## 사전 준비 (Prerequisites)

실행하려면 아래 3가지가 모두 준비돼 있어야 합니다. (GPU VRAM 12GB 이상 권장)

### 1) Python
- Python **3.10+** (개발 환경 기준 3.10)

### 2) Ollama + LLM 모델 (대화 담당)
1. [Ollama](https://ollama.com) 설치 → 실행(기본 포트 `11434`)
2. 모델 다운로드:
   ```bash
   ollama pull huihui_ai/gemma-4-abliterated:12b-qat
   ```
   - `abliterated`(검열 해제) 버전이어야 롤플레이가 막히지 않습니다.
   - 설치 확인: `ollama list` 에 위 모델이 보이면 OK.
   - 더 가벼운 변형을 쓰려면 `:e4b` 등으로 교체 가능하나, 대화 품질은 12b 쪽이 좋습니다.

### 3) ComfyUI + 이미지 모델 (초상·장면 이미지 담당)
1. [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 설치 → 실행(기본 포트 `8188`)
   - (StabilityMatrix 등으로 설치해도 됩니다.)
2. 아래 모델 파일을 ComfyUI 모델 폴더에 배치:
   | 종류 | 파일명 | 위치 |
   |---|---|---|
   | 체크포인트 | `noobaiXLNAIXL_epsilonPred11Version.safetensors` | `ComfyUI/models/checkpoints/` |
   | VAE | `sdxl-vae-fp16-fix.safetensors` | `ComfyUI/models/vae/` |
   - 체크포인트: **NoobAI-XL (NAI-XL) EPS** 계열 (Civitai / HuggingFace).
   - VAE: `madebyollin/sdxl-vae-fp16-fix` (HuggingFace). — 애니 SDXL의 색 뭉개짐 방지용.

> **ComfyUI 워크플로우(json)는 따로 불러올 필요가 없습니다.**
> 앱이 `backend/image_gen.py`에서 워크플로우를 **API로 직접 구성**해 ComfyUI에 전송합니다.
> ComfyUI는 **실행 상태 + 위 모델만** 있으면 됩니다. (별도 커스텀 노드도 불필요)

---

## 설치 & 실행

```bash
pip install -r requirements.txt
```

Ollama와 ComfyUI를 먼저 켠 뒤, 아래 둘 중 하나로 실행합니다.

### A. 데스크톱 창으로 실행 (권장)
```bash
cd backend
python launcher.py
```
→ 네이티브 창으로 UI가 열립니다.

### B. 웹 브라우저로 실행 (개발용)
```bash
cd backend
uvicorn main:app --reload --port 8010
```
→ 브라우저에서 `http://localhost:8010` 접속.

### C. 단일 실행파일(.exe)로 빌드
`PACKAGING.md` 참조. 요약:
```bash
pip install pyinstaller
pyinstaller --onefile --name CharacterChat --add-data "frontend;frontend" ^
  --collect-submodules uvicorn --collect-all webview backend/launcher.py
```
→ `dist/CharacterChat.exe` (실행 시 exe 옆 `data/`에 데이터 저장. 쓰기 가능한 폴더에서 실행할 것)

---

## 설정 변경

모델명·포트가 다르면 아래를 수정합니다.

- **LLM 모델 / Ollama 주소**: `backend/engine.py` 상단 `MODEL`, `OLLAMA_URL`, `OLLAMA_GEN_URL`
- **이미지 체크포인트·VAE·샘플러·해상도 / ComfyUI 주소**: `backend/image_gen.py` 상단 `CONFIG`
  (`CKPT_NAME`, `VAE_NAME`, `CLIP_SKIP`, `WIDTH/HEIGHT`, `STEPS`, `CFG`, `SAMPLER`, `SCHEDULER`, `COMFYUI_URL`)

---

## 프로젝트 구조

```
backend/
  main.py          FastAPI 엔드포인트 (캐릭터 CRUD, 대화, 초상/장면 이미지, 갤러리)
  engine.py        대화 엔진 (Ollama 연동, 상태 JSON, 호감도/신뢰도/상한해방)
  image_gen.py     ComfyUI 연동 (워크플로우 API 구성, 초상/장면 생성)
  store.py         파일 기반 저장 (캐릭터·세션·이미지)
  schema.py        캐릭터/플레이어 설정 스키마 (폼 자동 생성)
  settings_def.py  대화 설정 정의
  paths.py         개발/패키징 경로 해석
  launcher.py      데스크톱 런처 (pywebview + uvicorn)
frontend/          무프레임워크 UI (index.html / app.js / style.css)
data/              사용자 데이터 (캐릭터·세션·이미지) — git에 올리지 않음
```

---

## 참고 / 한계

- **VRAM 12GB**에서 LLM과 이미지 모델이 공존 불가 → 번갈아 올리는 양방향 직렬화로 처리(응답 ~30초).
- 캐릭터 얼굴 완전 고정은 미지원(태그+고정시드 기반의 '디자인 수준' 일관성). LoRA는 향후 과제.
- Ollama·ComfyUI는 수 GB 모델을 가진 외부 전제이므로, 범용 배포보다 **개인 사용·시연**에 적합합니다.
