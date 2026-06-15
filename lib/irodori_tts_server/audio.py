from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import soundfile as sf
import torch
import torchaudio

CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
}


def normalize_response_format(value: str | None, *, default: str) -> str:
    fmt = (default if value is None else str(value)).strip().lower()
    if fmt not in CONTENT_TYPES:
        allowed = ", ".join(sorted(CONTENT_TYPES))
        raise ValueError(f"Unsupported response_format={value!r}. Expected one of: {allowed}.")
    return fmt


def encode_audio(audio: torch.Tensor, sample_rate: int, response_format: str) -> bytes:
    fmt = normalize_response_format(response_format, default="mp3")
    wav = audio.detach().cpu().float()
    if wav.ndim == 1:
        wav = wav.unsqueeze(0)
    if wav.ndim != 2:
        raise ValueError(f"Expected audio shape (channels, samples), got {tuple(wav.shape)}")
    wav = wav.clamp(-1.0, 1.0).contiguous()

    if fmt == "pcm":
        pcm = (wav.squeeze(0).numpy() * 32767.0).astype("<i2", copy=False)
        return pcm.tobytes()

    buffer = BytesIO()
    if fmt in {"wav", "flac"}:
        sf.write(
            buffer,
            wav.transpose(0, 1).numpy(),
            int(sample_rate),
            format=fmt.upper(),
        )
        return buffer.getvalue()

    try:
        return _encode_with_torchaudio(wav, int(sample_rate), fmt)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to encode audio as {fmt}. Install FFmpeg-enabled torchaudio, "
            "or request response_format='wav'/'flac'/'pcm'."
        ) from exc


def _torchaudio_format(fmt: str) -> str:
    if fmt == "opus":
        return "ogg"
    if fmt == "aac":
        return "adts"
    return fmt


def _torchaudio_suffix(fmt: str) -> str:
    if fmt == "opus":
        return ".opus"
    if fmt == "aac":
        return ".aac"
    return f".{fmt}"


def _encode_with_torchaudio(wav: torch.Tensor, sample_rate: int, fmt: str) -> bytes:
    with TemporaryDirectory() as directory:
        path = Path(directory) / f"speech{_torchaudio_suffix(fmt)}"
        torchaudio.save(
            str(path),
            wav,
            sample_rate,
            format=_torchaudio_format(fmt),
        )
        return path.read_bytes()
