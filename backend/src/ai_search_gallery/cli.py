"""``gallery`` command: start the whole app and open it in the browser.

    uv run gallery                 # http://127.0.0.1:8000, opens a browser tab
    uv run gallery --no-browser
    uv run gallery --port 8001

One process serves the API and the built frontend; it starts the indexer as
its child process. If the app is already running on that port, the command
only opens the browser tab.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# The app modules (app, indexer, utils, ...) live next to this package in src/.
SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _is_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=1) as resp:
            return resp.status == 200
    except OSError:
        return False


def _open_when_ready(url: str) -> None:
    for _ in range(600):
        if _is_up(url):
            webbrowser.open(url)
            return
        time.sleep(0.5)


def main() -> None:
    from utils import config

    parser = argparse.ArgumentParser(prog="gallery", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=config.HOST)
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    if _is_up(url):
        print(f"AI Search Gallery is already running: {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    print(f"AI Search Gallery: {url}  (data: {config.DATA_DIR})")
    print("Stop with Ctrl+C.")
    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()

    import uvicorn
    from app import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
