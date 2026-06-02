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
from pydantic import BaseModel

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


def _path_to_file_uri(path: str) -> str:
    """AAF Locator 用の file URI を返す。"""

    try:
        return Path(path).resolve().as_uri()
    except Exception:
        return "file:///" + path.replace("\\", "/")


class AafClipPayload(BaseModel):
    name: str
    sourcePath: str
    timelineStart: float
    sourceStart: float
    duration: float


class AafTrackPayload(BaseModel):
    name: str
    clips: list[AafClipPayload]


class AafPayload(BaseModel):
    sampleRate: int
    tracks: list[AafTrackPayload]


class AafExportOptions(BaseModel):
    filename: str
    saveMode: str = "save"


class AafExportRequest(BaseModel):
    options: AafExportOptions
    aaf: AafPayload


def _safe_aaf_filename(filename: str) -> str:
    """AAF 書き出し用ファイル名を安全な単一ファイル名に整える。"""

    return _safe_export_filename(filename, "aaf")


def _seconds_to_units(seconds: float, edit_rate: int) -> int:
    """秒を AAF の edit unit に変換する。"""

    return max(0, int(round(seconds * edit_rate)))


# soundfile の subtype → (ビット深度, 1サンプルあたりバイト数)
_SUBTYPE_BITS = {
    "PCM_S8": (8, 1),
    "PCM_U8": (8, 1),
    "PCM_16": (16, 2),
    "PCM_24": (24, 3),
    "PCM_32": (32, 4),
    "FLOAT": (32, 4),
    "DOUBLE": (64, 8),
}


def _probe_audio_format(source_path: str, fallback_rate: int) -> dict:
    """実ファイルからチャンネル数・サンプルレート・ビット深度を読む。

    読めない場合は安全側のフォールバック（モノラル・16bit）を返す。
    """

    info = {
        "channels": 1,
        "sample_rate": fallback_rate,
        "bit_depth": 16,
        "bytes_per_sample": 2,
    }
    try:
        import soundfile as sf

        meta = sf.info(source_path)
        info["channels"] = max(1, int(meta.channels))
        info["sample_rate"] = int(meta.samplerate) or fallback_rate
        bits, bps = _SUBTYPE_BITS.get(meta.subtype, (16, 2))
        info["bit_depth"] = bits
        info["bytes_per_sample"] = bps
    except Exception:
        # ファイルが存在しない／soundfile 非対応フォーマット等はフォールバック。
        pass
    return info


def _make_external_source(
    f,
    source_path: str,
    source_name: str,
    source_length: int,
    edit_rate: str,
    audio_format: dict,
):
    """外部ファイル参照の MasterMob を作成する。"""

    # SourceMob: 外部ファイルへの参照（PCMDescriptor + NetworkLocator）
    source = f.create.SourceMob(f"{source_name} source")
    f.content.mobs.append(source)

    channels = audio_format["channels"]
    sample_rate = audio_format["sample_rate"]
    bit_depth = audio_format["bit_depth"]
    block_align = audio_format["bytes_per_sample"] * channels
    sr_rational = f"{sample_rate}/1"

    # PCMDescriptor: チャンネル数・サンプルレート・ビット深度を持つ音声フォーマット記述。
    descriptor = f.create.PCMDescriptor()
    descriptor["SampleRate"].value = sr_rational
    descriptor["AudioSamplingRate"].value = sr_rational
    descriptor["Channels"].value = channels
    descriptor["QuantizationBits"].value = bit_depth
    descriptor["BlockAlign"].value = block_align
    descriptor["AverageBPS"].value = sample_rate * block_align
    descriptor["Length"].value = source_length
    locator = f.create.NetworkLocator()
    locator["URLString"].value = _path_to_file_uri(source_path)
    # Locator は StrongRefVectorProperty。.value.append() はコピーへの操作で
    # 本体に反映されないため、プロパティへ直接 append する。
    descriptor["Locator"].append(locator)
    source.descriptor = descriptor

    # SourceMob のスロット: Sequence に終端 SourceClip（mob_id=0）を追加
    source_slot = source.create_empty_sequence_slot(edit_rate, 1, media_kind="sound")
    tape_clip = f.create.SourceClip(media_kind="sound")
    tape_clip.length = source_length
    source_slot.segment.components.append(tape_clip)
    source_slot.segment.length = source_length

    # MasterMob: SourceMob への参照
    master = f.create.MasterMob(source_name)
    f.content.mobs.append(master)
    master_slot = master.create_empty_sequence_slot(edit_rate, 1, media_kind="sound")
    master_slot.segment.components.append(
        source.create_source_clip(slot_id=1, start=0, length=source_length)
    )
    master_slot.segment.length = source_length

    return master


def _build_aaf_bytes(payload: AafPayload, filename: str) -> bytes:
    """AAF 編集リストを bytes として生成する。"""

    try:
        import aaf2
    except Exception as exc:
        raise HTTPException(status_code=500, detail="AAF 書き出しには pyaaf2 が必要です") from exc

    edit_rate_value = max(1, int(payload.sampleRate or 48000))
    edit_rate = f"{edit_rate_value}/1"
    # pyaaf2 はパス書き込み API のため一時ファイルを使う。
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".aaf", delete=False) as tmp:
        temp_file = Path(tmp.name)

    try:
        with aaf2.open(str(temp_file), "w") as f:
            composition = f.create.CompositionMob(Path(filename).stem or "DAW Edit")
            f.content.mobs.append(composition)

            for track_index, track in enumerate(payload.tracks, start=1):
                slot = composition.create_empty_sequence_slot(
                    edit_rate,
                    track_index,
                    media_kind="sound",
                )
                sequence = slot.segment
                cursor = 0
                sorted_clips = sorted(track.clips, key=lambda clip: clip.timelineStart)

                for clip in sorted_clips:
                    start = _seconds_to_units(clip.timelineStart, edit_rate_value)
                    source_start = _seconds_to_units(clip.sourceStart, edit_rate_value)
                    length = _seconds_to_units(clip.duration, edit_rate_value)
                    if length <= 0:
                        continue
                    if start > cursor:
                        sequence.components.append(
                            f.create.Filler(media_kind="sound", length=start - cursor)
                        )
                    elif start < cursor:
                        # AAF Sequence は重なりを表現しないため、重なるクリップは現在位置へ詰める。
                        start = cursor

                    source_length = max(source_start + length, length)
                    audio_format = _probe_audio_format(clip.sourcePath, edit_rate_value)
                    master = _make_external_source(
                        f,
                        clip.sourcePath,
                        Path(clip.sourcePath).name or clip.name,
                        source_length,
                        edit_rate,
                        audio_format,
                    )
                    sequence.components.append(
                        master.create_source_clip(slot_id=1, start=source_start, length=length)
                    )
                    cursor = start + length

                if cursor == 0:
                    sequence.components.append(f.create.Filler(media_kind="sound", length=1))
                    cursor = 1
                sequence.length = cursor

        return temp_file.read_bytes()
    finally:
        try:
            temp_file.unlink(missing_ok=True)
        except Exception:
            pass


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


@app.post("/api/daw/export-aaf")
async def api_daw_export_aaf(request: AafExportRequest):
    """DAW iframe から受け取った編集情報を AAF として保存/ダウンロードする。"""

    save_mode = request.options.saveMode
    if save_mode not in {"save", "download"}:
        raise HTTPException(status_code=400, detail="未対応の保存方法です")

    filename = _safe_aaf_filename(request.options.filename)
    out_bytes = _build_aaf_bytes(request.aaf, filename)

    if save_mode == "download":
        return StreamingResponse(
            io.BytesIO(out_bytes),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    cnfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    out_path = _unique_export_path(cnfg.outputs_dir, filename)
    out_path.write_bytes(out_bytes)
    return JSONResponse({"ok": True, "path": str(out_path)})
