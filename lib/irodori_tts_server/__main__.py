from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# lib/ をパスに追加して irodori_tts パッケージを解決する
_lib_dir = Path(__file__).resolve().parent.parent
if str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))

import uvicorn

from .config import get_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the Irodori-TTS OpenAI-compatible API.")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "irodori_tts_server.app:app",
        host=str(args.host),
        port=int(args.port),
        reload=bool(args.reload),
    )


if __name__ == "__main__":
    main()
