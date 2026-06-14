from __future__ import annotations

import hashlib
import json
import os
import sys
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.file_util import Mtdt, audio_files_in_folder
from voice.voicefile import VoiceFile



import torch
from tqdm import tqdm

from lib.irodori_tts.codec import DACVAECodec
from lib.irodori_tts.text_normalization import normalize_text

LOG_EVERY = 100
SEED = 42
TARGET_SAMPLE_RATE = 24000
CODEC_REPO = "Aratako/Semantic-DACVAE-Japanese-32dim"


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(x) for x in value)
    return str(value)


def _sanitize_id_component(value: Any, *, fallback: str) -> str:
    raw = _coerce_text(value).strip()
    if not raw:
        return fallback
    # Keep Unicode letters/digits (e.g. non-ASCII speaker IDs), while removing
    # separators/control chars that can break parsing or downstream tooling.
    s = unicodedata.normalize("NFKC", raw)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[:/\\\\]+", "-", s)
    s = re.sub(r"[\x00-\x1f\x7f]", "", s)
    s = re.sub(r"[^\w.\-]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-_.")
    if not s:
        s = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    if len(s) > 96:
        digest = hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]
        s = f"{s[:80]}-{digest}"
    return s


def _resolve_speaker_namespace(output_path: Path) -> str:
    """出力フォルダ名から speaker_id の namespace を決める。"""
    return _sanitize_id_component(output_path.name, fallback="project")


def _default_device() -> str:
    """利用可能なら CUDA、なければ CPU を使う。"""
    return "cuda" if torch.cuda.is_available() else "cpu"


def _coerce_audio_file(path: str, target_sample_rate: int | None) -> tuple[torch.Tensor, int]:
    """音声ファイルを読み込み、DACVAE に渡せる channel-first Tensor に変換する。"""
    import librosa

    wav_array, sr = librosa.load(path, sr=target_sample_rate, mono=False)
    wav = torch.as_tensor(wav_array).float()
    if wav.ndim == 1:
        wav = wav.unsqueeze(0)
    elif wav.ndim == 2:
        wav = wav.contiguous()
    else:
        raise ValueError(f"Unsupported decoded audio shape: {tuple(wav.shape)}")
    if wav.numel() == 0:
        raise ValueError("Decoded audio is empty")
    return wav, int(sr)


@dataclass
class _PreparedItem:
    idx: int
    status: str  # "ok", "skip", "error"
    text: str | None = None
    caption: str | None = None
    wav: torch.Tensor | None = None
    sample_rate: int | None = None
    speaker_id: str | None = None
    skip_reason: str | None = None
    error: str | None = None


def _prepare_voice_file(idx: int, voice_file: VoiceFile, args: SimpleNamespace) -> _PreparedItem:
    """VoiceFile から irodori-tts 用の前処理アイテムを作る。"""
    try:
        text = _coerce_text(voice_file.transcript)
        text = normalize_text(text)
        text = text.strip()

        caption = _coerce_text(voice_file.caption).strip() or None
        if not text:
            return _PreparedItem(idx=idx, status="skip", skip_reason="empty_text")

        speaker_id: str | None = None
        speaker_component = _sanitize_id_component(voice_file.speaker_id, fallback="")
        if speaker_component:
            speaker_id = f"{args.speaker_id_namespace}:{speaker_component}"

        try:
            wav, sr = _coerce_audio_file(voice_file.path, TARGET_SAMPLE_RATE)
        except Exception as exc:
            return _PreparedItem(
                idx=idx,
                status="skip",
                skip_reason="audio_decode",
                error=str(exc),
            )

        if args.max_seconds is not None:
            wav = wav[:, : int(args.max_seconds * sr)]
            if wav.numel() == 0:
                return _PreparedItem(idx=idx, status="skip", skip_reason="trimmed_empty")

        return _PreparedItem(
            idx=idx,
            status="ok",
            text=text,
            caption=caption,
            wav=wav,
            sample_rate=sr,
            speaker_id=speaker_id,
        )
    except Exception as exc:
        return _PreparedItem(
            idx=idx,
            status="error",
            skip_reason="prepare_error",
            error=str(exc),
        )


def _load_voice_files(paths: list[str], *, good_only: bool = False) -> list[VoiceFile]:
    """フォルダパス一覧から mtdt.json を考慮して VoiceFile を読み込む。"""
    voice_files: list[VoiceFile] = []
    for path in paths:
        folder = Path(path)
        mtdt_path = folder / "mtdt.json"
        mtdt = Mtdt(mtdt_path) if mtdt_path.exists() else None
        for file in audio_files_in_folder(folder):
            vf = VoiceFile.from_audio_file(file, mtdt)
            if good_only and not vf.good:
                continue
            voice_files.append(vf)
    return voice_files


def _iter_voice_files(
    voice_files: list[VoiceFile],
    *,
    args: SimpleNamespace,
) -> Iterable[_PreparedItem]:
    """VoiceFile 一覧を PreparedItem として順に返す。"""
    def _iter() -> Iterable[_PreparedItem]:
        for idx in range(len(voice_files)):
            yield _prepare_voice_file(idx, voice_files[idx], args)

    return _iter()


def _run_worker(args: SimpleNamespace) -> None:
    device = torch.device(_default_device())
    if device.type == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA/ROCm requested but not available.")
        if device.index is None:
            device = torch.device("cuda:0")
        torch.cuda.set_device(device)

    torch.manual_seed(SEED)

    output_path = Path(args.output_path).expanduser().resolve()
    args.speaker_id_namespace = _resolve_speaker_namespace(output_path)
    output_manifest = output_path / "train_manifest.jsonl"
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest_base = output_manifest.parent

    latent_dir = output_path / "latent"
    latent_dir.mkdir(parents=True, exist_ok=True)

    voice_files = _load_voice_files(args.paths, good_only=args.good_only)

    codec = DACVAECodec.load(
        repo_id=CODEC_REPO,
        device=str(device),
        deterministic_encode=True,
        deterministic_decode=True,
    )

    total: int | None = len(voice_files)

    written = 0
    seen = 0
    skip_counts: dict[str, int] = {}
    pbar = tqdm(
        total=total,
        desc="Precompute latents",
        unit="utt",
        dynamic_ncols=True,
    )

    def _inc_skip(reason: str | None) -> None:
        key = reason or "unknown"
        skip_counts[key] = skip_counts.get(key, 0) + 1

    def _log_progress() -> None:
        if seen <= 0 or seen % LOG_EVERY != 0:
            return
        skipped_empty = skip_counts.get("empty_text", 0)
        skipped_speaker = skip_counts.get("missing_speaker", 0)
        skipped_audio = sum(
            skip_counts.get(k, 0)
            for k in (
                "audio_decode",
                "trimmed_empty",
                "prepare_error",
                "encode_error",
                "dataset_iter_error",
            )
        )
        total_msg = f"/{total}" if total is not None else ""
        message = (
            f"seen={seen}{total_msg} written={written} "
            f"skipped_empty={skipped_empty} "
            f"skipped_speaker={skipped_speaker} "
            f"skipped_audio={skipped_audio}"
        )
        pbar.set_postfix(
            {
                "written": written,
                    "skip": (
                        skipped_empty
                        + skipped_speaker
                        + skipped_audio
                    ),
            },
            refresh=False,
        )

    def _handle_item(item: _PreparedItem, *, out_f) -> None:
        nonlocal seen, written
        seen += 1
        pbar.update(1)

        if item.status == "skip":
            _inc_skip(item.skip_reason)
            _log_progress()
            return
        if item.status == "error":
            _inc_skip(item.skip_reason or "prepare_error")
            _log_progress()
            return
        wav = item.wav
        sr = item.sample_rate
        text = item.text
        caption = item.caption
        speaker_id = item.speaker_id
        if wav is None or sr is None or text is None:
            _inc_skip("prepare_error")
            _log_progress()
            return

        try:
            with torch.inference_mode():
                latent = codec.encode_waveform(wav, sample_rate=sr)[0].cpu()
        except Exception:
            _inc_skip("encode_error")
            _log_progress()
            return

        latent_name = f"{written:08d}_{item.idx:08d}.pt"
        latent_path = (latent_dir / latent_name).resolve()
        torch.save(latent, latent_path)
        latent_rel = Path(os.path.relpath(latent_path, start=manifest_base)).as_posix()
        payload = {
            "text": text,
            "latent_path": latent_rel,
            "num_frames": int(latent.shape[0]),
        }
        if caption is not None:
            payload["caption"] = caption
        if speaker_id is not None:
            payload["speaker_id"] = speaker_id
        out_f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        written += 1
        _log_progress()

    iter_items = _iter_voice_files(voice_files, args=args)
    with output_manifest.open("w", encoding="utf-8") as out_f:
        try:
            for entry in iter_items:
                _handle_item(entry, out_f=out_f)
        finally:
            out_f.flush()
            pbar.close()

    skipped_empty = skip_counts.get("empty_text", 0)
    skipped_speaker = skip_counts.get("missing_speaker", 0)
    skipped_audio = sum(
        skip_counts.get(k, 0)
        for k in (
            "audio_decode",
            "trimmed_empty",
            "prepare_error",
            "encode_error",
            "dataset_iter_error",
        )
    )
    print(
        f"done. seen={seen} written={written} "
        f"skipped_empty={skipped_empty} "
        f"skipped_speaker={skipped_speaker} "
        f"skipped_audio={skipped_audio} manifest={output_manifest}"
    , flush=True)
    if skip_counts:
        print("skip breakdown:", flush=True)
        for reason, count in sorted(skip_counts.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {reason}: {count}", flush=True)


def main() -> None:
    """stdin の JSON から設定を受け取って latent manifest を作成する。"""
    data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    args = SimpleNamespace(
        paths=data["paths"],
        output_path=data["output_path"],
        max_seconds=data.get("max_seconds"),
        good_only=data.get("good_only", False),
    )
    if args.good_only:
        print("good=True のファイルのみを対象とします", flush=True)
    print("トレーニングデータ作成開始", flush=True)
    _run_worker(args)


if __name__ == "__main__":
    main()
