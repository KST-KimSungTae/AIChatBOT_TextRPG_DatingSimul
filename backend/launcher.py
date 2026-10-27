# -*- coding: utf-8 -*-
"""데스크톱 런처.

FastAPI 서버를 백그라운드 스레드로 띄우고, pywebview 네이티브 창으로 UI를 연다.
→ 사용자는 '하나의 프로그램'(캐릭터 챗 창)만 실행하면 된다.

전제(별도 실행 필요): Ollama(localhost:11434), ComfyUI(localhost:8188).
  두 모델은 수 GB 용량이라 실행파일에 포함하지 않는다. 앱 내에서 연결 실패 시 안내 메시지를 띄운다.

개발 중 창으로 띄워 확인:  python launcher.py
"""
import socket
import threading
import time

import uvicorn
import webview   # pywebview

from main import app

HOST = "127.0.0.1"
WINDOW_TITLE = "캐릭터 챗"


class Api:
    """pywebview JS API. 프론트에서 window.pywebview.api.quit() 로 창을 닫는다."""
    def quit(self):
        for w in list(webview.windows):
            try:
                w.destroy()
            except Exception:
                pass


def _find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _run_server(port):
    # reload=False (패키징 환경). 로그는 조용히.
    uvicorn.run(app, host=HOST, port=port, log_level="warning")


def _wait_until_up(port, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main():
    port = _find_free_port()
    threading.Thread(target=_run_server, args=(port,), daemon=True).start()
    _wait_until_up(port)   # 서버가 응답할 때까지 대기(최대 15초)

    webview.create_window(
        WINDOW_TITLE,
        f"http://{HOST}:{port}",
        js_api=Api(),
        width=1280, height=860,
        min_size=(1120, 720),   # 이보다 작아지면 2단 레이아웃이 깨지므로 최소 크기 고정
    )
    webview.start()   # 창이 닫히면 반환 → 데몬 서버 스레드도 함께 종료


if __name__ == "__main__":
    main()
