from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from nicegui import app


_DAW_DEV_URL = "http://127.0.0.1:5173"
_DAW_DIST = Path(__file__).parent.parent / "daw" / "dist"
_DAW_STATIC_REGISTERED = _DAW_DIST.exists()

if _DAW_STATIC_REGISTERED:
    app.add_static_files("/daw", str(_DAW_DIST))


@dataclass
class DawTrack:
    """DAW へ渡すトラック情報。"""

    id: str
    name: str
    sourcePath: str
    url: str
    volume: float = 1.0
    muted: bool = False
    soloed: bool = False
    startTime: float = 0.0


@dataclass
class DawSession:
    """DAW 編集セッションの一時情報。"""

    id: str
    tracks: list[DawTrack]


_sessions: dict[str, DawSession] = {}


def create_daw_session(paths: list[str]) -> DawSession:
    """音声ファイルパスから DAW セッションを作成する。"""

    session_id = uuid4().hex
    tracks: list[DawTrack] = []

    for index, path in enumerate(paths):
        source = Path(path).resolve()
        mount = f"/daw-media/{session_id}/{index}"
        app.add_media_files(mount, str(source.parent))
        tracks.append(
            DawTrack(
                id=str(index),
                name=source.name,
                sourcePath=str(source),
                url=f"{mount}/{source.name}",
            )
        )

    session = DawSession(id=session_id, tracks=tracks)
    _sessions[session_id] = session
    return session


def get_daw_session(session_id: str) -> DawSession | None:
    """セッション ID から DAW セッションを取得する。"""

    return _sessions.get(session_id)


def get_daw_url(session_id: str) -> str:
    """React DAW の URL を返す。"""

    if _DAW_STATIC_REGISTERED:
        return f"/daw/index.html?session={session_id}"
    return f"{_DAW_DEV_URL}/?session={session_id}"


@app.get("/api/daw/session/{session_id}")
def api_daw_session(session_id: str) -> dict:
    """React DAW の初期化情報を返す。"""

    session = get_daw_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="DAW セッションが見つかりません")
    return {
        "id": session.id,
        "tracks": [asdict(track) for track in session.tracks],
    }
