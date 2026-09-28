# AI Character Chatbot — Text RPG + Dating Sim

로컬에서 구동하는 캐릭터 AI 챗봇. 오픈소스 LLM(로컬)과 이미지 생성 모델을 활용해,
사용자가 직접 만든 캐릭터와 대화하고 관계가 변화하는 텍스트 RPG / 연애 시뮬레이션.

## 특징
- 사용자가 성격·말투·배경·관계·플레이어 페르소나까지 커스텀하는 캐릭터 생성
- 호감도 · 기분 · 기억을 실시간으로 추적하는 상태 패널
- 대화 흐름에 따라 감정과 관계가 변화 (호감도 감쇠 곡선, 특별한 순간 시스템)
- 로컬 LLM(Ollama) 기반 — 대화 상태를 디스크에 저장/복원

## 기술 스택
- 백엔드: Python, FastAPI
- 프론트엔드: HTML / CSS / JavaScript (프레임워크 없음)
- LLM 서빙: Ollama (로컬)
- 이미지 생성(예정): ComfyUI + SDXL 계열

## 실행
```
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
브라우저에서 http://localhost:8000 접속. (Ollama가 로컬에서 실행 중이어야 함)

## 구조
```
backend/    FastAPI 서버, 대화 엔진, 캐릭터/세션 저장
frontend/   웹 UI (캐릭터 목록 · 생성 · 대화)
data/       캐릭터·대화 데이터 (git에 올리지 않음, 로컬 전용)
```
