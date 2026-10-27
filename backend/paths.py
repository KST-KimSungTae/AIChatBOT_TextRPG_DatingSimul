# -*- coding: utf-8 -*-
"""실행 환경에 따라 리소스·데이터 경로를 해석한다.

- 개발 실행(uvicorn): backend/ 의 상위(프로젝트 루트)를 기준.
- 패키징 실행(PyInstaller .exe, sys.frozen):
    · 번들된 읽기 전용 리소스(frontend 등)는 _MEIPASS 임시 추출 폴더.
    · 사용자 데이터(data/)는 exe 옆의 쓰기 가능한 폴더.
"""
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    # PyInstaller onefile: 번들 리소스는 _MEIPASS(임시, 읽기 전용)
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # 사용자 데이터는 exe 옆에 둬서 재실행·업데이트 후에도 유지되게 한다.
    DATA_ROOT = Path(sys.executable).parent / "data"
else:
    _root = Path(__file__).resolve().parent.parent   # backend/ 의 상위 = 프로젝트 루트
    RESOURCE_DIR = _root
    DATA_ROOT = _root / "data"

FRONTEND_DIR = RESOURCE_DIR / "frontend"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
