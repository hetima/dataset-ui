from __future__ import annotations

from dataclasses import dataclass, asdict
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

from fastapi import File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from nicegui import app

from common.setting import cnfg


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


def _safe_export_filename(filename: str, fmt: str) -> str:
    """書き出し用ファイル名を安全な単一ファイル名に整える。"""

    stem = Path(filename or "daw-export").stem
    stem = re.sub(r'[\\/:*?"<>|]+', "_", stem).strip()
    if not stem:
        stem = "daw-export"
    return f"{stem}.{fmt}"


def _unique_export_path(directory: Path, filename: str) -> Path:
    """同名ファイルがある場合は stem に _数字 を付けた保存先を返す。"""

    path = directory / filename
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    index = 1
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _convert_wav_bytes(wav_bytes: bytes, fmt: str) -> tuple[bytes, str]:
    """WAV bytes を指定フォーマットの bytes に変換する。"""

    if fmt == "wav":
        return wav_bytes, "audio/wav"

    if fmt != "flac":
        raise HTTPException(status_code=400, detail="未対応のフォーマットです")

    try:
        import soundfile as sf
    except Exception:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise HTTPException(status_code=500, detail="FLAC 変換には soundfile または ffmpeg が必要です")
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "wav", "-i", "pipe:0", "-f", "flac", "pipe:1"],
            input=wav_bytes,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            message = proc.stderr.decode("utf-8", errors="ignore") or "ffmpeg による FLAC 変換に失敗しました"
            raise HTTPException(status_code=500, detail=message)
        return proc.stdout, "audio/flac"

    data, samplerate = sf.read(io.BytesIO(wav_bytes), always_2d=True, dtype="float32")
    out = io.BytesIO()
    sf.write(out, data, samplerate, format="FLAC")
    return out.getvalue(), "audio/flac"


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


@app.post("/api/daw/export")
async def api_daw_export(
    audio: UploadFile = File(...),
    options: str = Form(...),
):
    """DAW iframe から受け取った WAV を保存/変換/ダウンロードする。"""

    try:
        opts = json.loads(options)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="書き出し設定の JSON が不正です") from exc

    fmt = str(opts.get("format", "wav")).lower()
    if fmt not in {"wav", "flac"}:
        raise HTTPException(status_code=400, detail="未対応のフォーマットです")
    save_mode = str(opts.get("saveMode", "save"))
    if save_mode not in {"save", "download"}:
        raise HTTPException(status_code=400, detail="未対応の保存方法です")

    filename = _safe_export_filename(str(opts.get("filename", "daw-export")), fmt)
    wav_bytes = await audio.read()
    out_bytes, media_type = _convert_wav_bytes(wav_bytes, fmt)

    if save_mode == "download":
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    cnfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    out_path = _unique_export_path(cnfg.outputs_dir, filename)
    out_path.write_bytes(out_bytes)
    return JSONResponse({"ok": True, "path": str(out_path)})
