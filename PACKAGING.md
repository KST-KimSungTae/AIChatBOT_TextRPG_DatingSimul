# 패키징 가이드 — 하나의 실행 프로그램(.exe)

챗봇 본체(FastAPI 백엔드 + 정적 프론트엔드)를 **pywebview 창 + PyInstaller 단일 .exe**로 묶는다.
사용자는 `CharacterChat.exe` 하나만 실행하면 네이티브 창으로 UI가 뜬다.

> **전제(별도 실행 필요):** `Ollama`(localhost:11434)와 `ComfyUI`(localhost:8188).
> 두 모델은 수 GB라 .exe 안에 포함하지 않는다. 미실행 시 앱 안에서 연결 실패 안내가 뜬다.
> (게임이 GPU 드라이버·런타임을 요구하는 것과 같은 맥락.)

---

## 구성 요소 (이번에 추가/변경된 것)

| 파일 | 역할 |
|---|---|
| `backend/paths.py` (신규) | 개발 vs 패키징(.exe) 환경에 맞춰 **frontend·data 경로**를 해석 |
| `backend/launcher.py` (신규) | uvicorn을 백그라운드로 띄우고 **pywebview 창**으로 UI를 여는 진입점 |
| `backend/store.py` (변경) | 데이터 경로를 `paths.DATA_ROOT` 기준으로 (exe 옆 `data/`에 저장) |
| `backend/main.py` (변경) | 정적 파일 경로를 `paths.FRONTEND_DIR` 기준으로 |
| `requirements.txt` (변경) | `pywebview` 추가 |

**데이터 저장 위치:** 패키징 실행 시 **exe 옆 `data/` 폴더**에 캐릭터·세션·이미지가 저장된다
(재실행·업데이트 후에도 유지). → **쓰기 가능한 폴더에서 exe를 실행**할 것(Program Files 같은 보호 폴더 X).

---

## 1. 개발 중 창으로 확인 (빌드 전)

```bash
pip install -r requirements.txt
python backend/launcher.py
```
→ uvicorn이 뜨고 pywebview 창으로 UI가 열리면 런처 로직은 정상.
(Ollama·ComfyUI도 켜져 있어야 대화·이미지가 동작.)

---

## 2. 빌드 (Windows)

```bat
pip install -r requirements.txt pyinstaller

pyinstaller --onefile --name CharacterChat ^
  --add-data "frontend;frontend" ^
  --collect-submodules uvicorn ^
  --collect-all webview ^
  backend/launcher.py
```

- `--onefile` : 단일 .exe
- `--add-data "frontend;frontend"` : 정적 UI를 번들에 포함 (Windows는 구분자 `;`)
- `--collect-submodules uvicorn` : uvicorn의 동적 import 포함(빠지면 서버가 안 뜸)
- `--collect-all webview` : pywebview 플랫폼 백엔드 포함
- 처음엔 **콘솔 창을 켠 채로** 빌드(에러 로그가 보임). 안정화되면 아래로 **콘솔 숨김**:
  ```bat
  pyinstaller ... --noconsole backend/launcher.py
  ```

**결과:** `dist\CharacterChat.exe`
처음 실행하면 `dist\` 안에 `data\` 폴더가 생기고 거기에 모든 사용자 데이터가 쌓인다.

> 재빌드 시 자동 생성된 `CharacterChat.spec`을 커밋해두면, 다음부턴 `pyinstaller CharacterChat.spec`로 재현 가능.

---

## 3. 실행

1. **Ollama** 실행 + 모델 보유 (`ollama list`에 `huihui_ai/gemma-4-abliterated:12b-qat`)
2. **ComfyUI** 실행 (localhost:8188, NoobAI 체크포인트 로드)
3. `CharacterChat.exe` 더블클릭 → 창이 뜸

---

## 4. 자주 나는 빌드/실행 이슈

- **실행 시 창은 뜨는데 UI가 안 보임 / 흰 화면**
  → `--add-data "frontend;frontend"`가 빠졌거나 경로 구분자가 `:`(리눅스용)로 들어간 경우. Windows는 `;`.
- **"ModuleNotFoundError: uvicorn.loops..." 류**
  → `--collect-submodules uvicorn` 누락. 추가 후 재빌드.
- **pywebview 창이 안 뜨거나 백엔드 에러**
  → `--collect-all webview` 확인. Win10/11은 Edge **WebView2 런타임**이 보통 기본 설치돼 있으나, 없으면
    MS WebView2 Runtime을 설치. (대안: `pip install pywebview[cef]` 후 CEF 백엔드 사용)
- **"data 폴더에 쓸 수 없음" / 캐릭터가 저장 안 됨**
  → exe를 Program Files 등 보호 폴더가 아니라 **일반 폴더**(바탕화면 등)에서 실행.
- **첫 실행이 느림**
  → onefile은 매 실행 시 임시 폴더로 압축 해제. 빠른 기동이 필요하면 `--onefile` 대신 `--onedir`(폴더 배포).

---

## 5. 한계 / 향후

- Ollama·ComfyUI는 외부 전제. "원클릭 전체 기동"을 원하면, 런처에서 두 프로세스를 자동 실행·헬스체크하는
  단계를 추가할 수 있음(설치 경로 탐지 필요 → 다음 단계 과제).
- 배포 대상에 GPU(VRAM 12GB+)와 모델 파일이 필요하므로, 범용 배포보다는 **포트폴리오 시연·개인 사용**이 현실적.
