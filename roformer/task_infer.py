"""ThreadTaskDialog 用 Roformer 推論タスク。"""
import queue
import threading
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Base configs
# ---------------------------------------------------------------------------
_MELBAND_BASE_CONFIG = {
    "stereo": True,
    "num_bands": 60,
    "dim_head": 64,
    "heads": 8,
    "attn_dropout": 0,
    "ff_dropout": 0,
    "flash_attn": True,
    "dim_freqs_in": 1025,
    "sample_rate": 44100,
    "stft_n_fft": 2048,
    "stft_hop_length": 441,
    "stft_win_length": 2048,
    "stft_normalized": False,
    "mask_estimator_depth": 2,
    "multi_stft_resolution_loss_weight": 1.0,
    "multi_stft_resolutions_window_sizes": (4096, 2048, 1024, 512, 256),
    "multi_stft_hop_size": 147,
    "multi_stft_normalized": False,
}

_BS_BASE_CONFIG = {
    "stereo": True,
    "dim_head": 64,
    "heads": 8,
    "attn_dropout": 0,
    "ff_dropout": 0,
    "flash_attn": True,
    "dim_freqs_in": 1025,
    "sample_rate": 44100,
    "stft_n_fft": 2048,
    "stft_hop_length": 441,
    "stft_win_length": 2048,
    "stft_normalized": False,
    "mask_estimator_depth": 2,
    "multi_stft_resolution_loss_weight": 1.0,
    "multi_stft_resolutions_window_sizes": (4096, 2048, 1024, 512, 256),
    "multi_stft_hop_size": 147,
    "multi_stft_normalized": False,
}

def _get_device():
    import torch
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")

def _offload_device():
    import torch
    return torch.device("cpu")


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
def _load_torch_file(path: str) -> dict:
    import torch
    if path.endswith(".safetensors"):
        from safetensors.torch import load_file
        return load_file(path)
    return torch.load(path, map_location="cpu", weights_only=False)


def _infer_shared_params(sd: dict, config: dict) -> None:
    config["dim"] = sd["band_split.to_features.0.1.weight"].shape[0]
    config["depth"] = max(int(k.split('.')[1]) for k in sd if k.startswith('layers.')) + 1
    config["num_stems"] = max(int(k.split('.')[1]) for k in sd if k.startswith('mask_estimators.')) + 1

    time_keys = [k for k in sd if k.startswith('layers.0.0.layers.')]
    config["time_transformer_depth"] = max(int(k.split('.')[4]) for k in time_keys) + 1 if time_keys else 1

    freq_keys = [k for k in sd if k.startswith('layers.0.1.layers.')]
    config["freq_transformer_depth"] = max(int(k.split('.')[4]) for k in freq_keys) + 1 if freq_keys else 1

    mlp_keys = [k for k in sd if k.startswith('mask_estimators.0.to_freqs.0.0.') and k.endswith('.weight')]
    if mlp_keys:
        config["mask_estimator_depth"] = max(int(k.split('.')[5]) for k in mlp_keys) // 2


def _detect_model_type(sd: dict) -> str:
    band_weights = [v for k, v in sd.items()
                    if k.startswith('band_split.to_features.') and k.endswith('.1.weight')]
    if not band_weights:
        return 'melband'
    total_input = sum(w.shape[1] for w in band_weights)
    return 'bsroformer' if total_input <= 4 * 1025 else 'melband'


def _infer_melband_config(sd: dict) -> dict:
    config = dict(_MELBAND_BASE_CONFIG)
    _infer_shared_params(sd, config)
    return config


def _infer_bs_roformer_config(sd: dict) -> dict:
    config = dict(_BS_BASE_CONFIG)
    _infer_shared_params(sd, config)
    band_keys = sorted(
        (int(k.split('.')[3]), k)
        for k in sd
        if k.startswith('band_split.to_features.') and k.endswith('.1.weight')
    )
    first_input = sd[band_keys[0][1]].shape[1]
    divisor = 4 if first_input % 4 == 0 else 2
    config["stereo"] = (divisor == 4)
    config["freqs_per_bands"] = tuple(sd[k].shape[1] // divisor for _, k in band_keys)
    return config


def _infer_config(sd: dict) -> tuple[str, dict]:
    model_type = _detect_model_type(sd)
    if model_type == 'bsroformer':
        return 'bsroformer', _infer_bs_roformer_config(sd)
    return 'melband', _infer_melband_config(sd)


def _recommended_chunk_size(model_name: str, config: dict) -> float:
    name = model_name.lower()
    num_stems = config.get("num_stems", 1)
    dim = config.get("dim", 256)
    if any(x in name for x in ("dereverb", "deverb", "echo")):
        base = 12.0
    elif any(x in name for x in ("denoise", "aspiration")):
        base = 6.0
    elif num_stems >= 4:
        base = 10.0
    else:
        base = 8.0
    if dim >= 512:
        base = max(4.0, base - 2.0)
    return base


def _filter_kwargs(cls, config: dict) -> dict:
    """cls.__init__ が受け付けるキーだけに絞る。"""
    import inspect
    params = inspect.signature(cls.__init__).parameters
    return {k: v for k, v in config.items() if k in params}


def _load_yaml(path: str) -> dict | None:
    """同名 yaml を丸ごと読んで返す。なければ None。"""
    yaml_path = Path(path).with_suffix(".yaml")
    if not yaml_path.exists():
        return None
    try:
        import yaml
        text = yaml_path.read_text(encoding="utf-8").replace("!!python/tuple", "")
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _load_yaml_model_config(path: str) -> dict | None:
    """同名 yaml の model: セクションを読んで返す。なければ None。"""
    data = _load_yaml(path)
    return data.get("model") if data else None


def _get_stem_labels(path: str, num_stems: int) -> list[str]:
    """yaml の training セクションから stem ラベルリストを返す。
    target_instrument あり → [target, ...残り instruments]
    target_instrument なし → instruments の順番
    yaml なし → ["", "_bg"] or ["_stem1", "_stem2", ...]
    """
    data = _load_yaml(path)
    training = data.get("training") if data else None
    if training:
        instruments: list[str] = training.get("instruments", [])
        target: str | None = training.get("target_instrument")
        if target:
            others = [i for i in instruments if i != target]
            labels = [target] + others
        else:
            labels = list(instruments)
        if labels:
            return [f"_{l}" for l in labels]
    # fallback
    return [f"_stem{i+1}" for i in range(num_stems)]


def load_model(path: str) -> Any:
    """モデルファイルをロードしてインスタンスを返す。yaml があれば model: セクションを config として使い、なければ state dict から自動検出する。"""
    from roformer.model.mel_band_roformer import MelBandRoformer
    sd = _load_torch_file(path)

    yaml_config = _load_yaml_model_config(path)
    if yaml_config is not None:
        config = yaml_config
        for key in ("freqs_per_bands", "multi_stft_resolutions_window_sizes"):
            if key in config and isinstance(config[key], list):
                config[key] = tuple(config[key])
        model_type = 'bsroformer' if 'freqs_per_bands' in config else 'melband'
    else:
        model_type, config = _infer_config(sd)

    if model_type == 'bsroformer':
        from roformer.model.bs_roformer import BSRoformer
        model = BSRoformer(**_filter_kwargs(BSRoformer, config)).eval()
    else:
        model = MelBandRoformer(**_filter_kwargs(MelBandRoformer, config)).eval()
    model.load_state_dict(sd, strict=True)
    return model


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
def _get_windowing_array(window_size: int, fade_size: int, dev: Any) -> Any:
    import torch
    fadein = torch.linspace(0, 1, fade_size)
    fadeout = torch.linspace(1, 0, fade_size)
    window = torch.ones(window_size)
    window[-fade_size:] *= fadeout
    window[:fade_size] *= fadein
    return window.to(dev)


def _run_inference(
    model: Any,
    audio_input: Any,
    chunk_size: float = 8.0,
    overlap: int = 2,
    fade_size_ratio: float = 0.1,
    batch_size: int = 1,
    progress_callback=None,
    stop_event: threading.Event | None = None,
) -> list:
    """
    audio_input: [channels, time] (44100Hz, stereo)
    戻り値: [num_stems] の Tensor リスト、各 [channels, time]
    """
    import torch
    import torch.nn.functional as F
    device = _get_device()
    offload_device = _offload_device()
    sr = 44100
    original_audio = audio_input
    audio_length = audio_input.shape[1]

    C = int(chunk_size * sr)
    step = C // overlap
    fade_samples = max(1, int(C * fade_size_ratio))
    border = C - step

    if audio_length > 2 * border and border > 0:
        audio_input = F.pad(audio_input, (border, border), mode='reflect')

    windowing_array = _get_windowing_array(C, fade_samples, device)
    audio_input = audio_input.to(device)
    num_stems = len(model.mask_estimators)
    total_length = audio_input.shape[1]
    chunk_starts = list(range(0, total_length, step))
    num_chunks = len(chunk_starts)

    acc = torch.zeros(num_stems, *audio_input.shape, dtype=torch.float32, device=device)
    cnt = torch.zeros(num_stems, *audio_input.shape, dtype=torch.float32, device=device)

    model.to(device)

    with torch.no_grad():
        for b_idx, b_start in enumerate(range(0, num_chunks, batch_size)):
            if stop_event is not None and stop_event.is_set():
                return []
            batch_starts = chunk_starts[b_start:b_start + batch_size]
            parts, lengths = [], []
            for i in batch_starts:
                part = audio_input[:, i:i + C]
                length = part.shape[-1]
                lengths.append(length)
                if length < C:
                    pad_mode = 'reflect' if length > C // 2 + 1 else 'constant'
                    part = F.pad(part, (0, C - length), mode=pad_mode)
                parts.append(part)

            batch_in = torch.stack(parts, dim=0)
            batch_out = model(batch_in)
            # MelBand: [batch, channels, time] → [batch, 1, channels, time]
            # BSRoformer: [batch, stems, channels, time] (そのまま)
            if batch_out.ndim == 3:
                batch_out = batch_out.unsqueeze(1)

            for idx, (i, length) in enumerate(zip(batch_starts, lengths)):
                out = batch_out[idx]  # [stems, channels, time]
                eff = min(length, out.shape[-1])
                window = windowing_array[:eff].clone()
                if i == 0:
                    window[:fade_samples] = 1
                if i + C >= total_length:
                    window[-fade_samples:] = 1
                acc[..., i:i + eff] += out[..., :eff] * window[..., :eff]
                cnt[..., i:i + eff] += window[..., :eff]

            if progress_callback:
                progress_callback(b_idx + 1, (num_chunks + batch_size - 1) // batch_size)

    model.to(offload_device)
    import gc
    estimated = acc / cnt.clamp(min=1e-8)
    del acc, cnt
    gc.collect()
    torch.cuda.empty_cache()

    if audio_length > 2 * border and border > 0:
        estimated = estimated[..., border:-border]

    if num_stems == 1:
        stem1 = estimated[0].cpu()
        stem2 = (original_audio - estimated[0].cpu())
        del estimated
        return [stem1, stem2]

    result = [estimated[i].cpu() for i in range(num_stems)]
    del estimated
    return result


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _unique_output_path(out_dir: str, stem_base: str, fmt: str) -> Path:
    """wav/flac 両方をチェックして重複しない出力パスを返す。"""
    def exists_any(base: Path) -> bool:
        return base.with_suffix(".wav").exists() or base.with_suffix(".flac").exists()

    candidate = Path(out_dir) / (stem_base + fmt)
    if not exists_any(candidate.with_suffix("")):
        return candidate
    n = 1
    while True:
        candidate = Path(out_dir) / (f"{stem_base}_{n}" + fmt)
        if not exists_any(candidate.with_suffix("")):
            return candidate
        n += 1


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
def _log(q: queue.Queue, text: str) -> None:  # type: ignore[type-arg]
    q.put({"type": "log", "text": text})


def infer_roformer(data: dict, q: queue.Queue, stop_event: threading.Event) -> dict | None:  # type: ignore[type-arg]
    """
    data keys:
      model     : dict  (list_roformer_models の1エントリ)
      suffix    : str   (出力ファイル名サフィックス)
      fmt       : str   (".wav" | ".flac")
      dest      : str   ("output_dir" | "same")
      cache     : bool  (モデルをキャッシュするか)
      files     : list[str]  (処理対象ファイルパス)
      output_dir: str   (dest=="output_dir" のときの出力先、空なら same 扱い)
    """
    import torch
    import torchaudio.functional as TAF
    import soundfile as sf
    from common.model_cache import model_cache

    model_info: dict = data["model"]
    suffix: str = data["suffix"]
    fmt: str = data["fmt"]
    cache: bool = data["cache"]
    files: list[str] = data["files"]
    output_dir: str = data.get("output_dir", "")

    model_name: str = model_info.get("name", "")
    model_path: str = model_info.get("path", "")

    # モデルロード（キャッシュ確認）
    entry = model_cache.get_entry(model_name)
    if cache and entry and entry.cached:
        _log(q, f"キャッシュ済みモデルを使用: {model_name}")
        model = entry.value
    else:
        # キャッシュオフ、またはキャッシュが取れなかった場合は既存キャッシュを全破棄
        if model_cache.entries:
            _log(q, "メモリ確保のため既存キャッシュを破棄します")
            model_cache.dispose_all()
            import gc
            gc.collect()
            torch.cuda.empty_cache()
        _log(q, f"モデルをロード中: {model_name}")
        try:
            model = load_model(model_path)
        except Exception as e:
            _log(q, f"[エラー] モデルロード失敗: {e}")
            return None
        _log(q, "モデルロード完了")
        if cache:
            model_cache.model_loaded(
                name=model_name,
                value=model,
                get_func=lambda: load_model(model_path),
                dispose_func=lambda _: None,
            )

    sr_target = 44100
    q.put({"type": "progress", "value": 0, "max": len(files)})

    for i, file_path in enumerate(files):
        if stop_event.is_set():
            return None

        _log(q, f"処理中 [{i+1}/{len(files)}]: {Path(file_path).name}")

        # 音声読み込み
        try:
            # audio_np, sr = sf.read(file_path, always_2d=True)  # [time, channels]
            audio_np, sr = load_audio_44k_librosa(file_path)  # [time, channels]
        except Exception as e:
            _log(q, f"  読み込みエラー: {e}")
            continue

        audio_tensor = torch.from_numpy(audio_np).float()  # [channels, time]

        if audio_tensor.shape[0] == 1:
            audio_tensor = audio_tensor.repeat(2, 1)

        if sr != sr_target:
            _log(q, f"  リサンプル {sr} → {sr_target}")
            audio_tensor = TAF.resample(audio_tensor, orig_freq=sr, new_freq=sr_target) # type: ignore

        # 推論
        def on_progress(step: int, total: int) -> None:
            _log(q, f"  チャンク {step}/{total}")

        try:
            stems = _run_inference(model, audio_tensor, chunk_size=float(data.get("chunk_size", 8.0)), overlap=data.get("overlap", 2), progress_callback=on_progress, stop_event=stop_event)
        except Exception as e:
            _log(q, f"  推論エラー: {e}")
            continue

        if not stems:
            return None

        # 出力先決定
        base_dir = output_dir if output_dir else str(Path(file_path).parent)
        if data.get("subfolder", False):
            out_dir = str(Path(base_dir) / Path(file_path).stem)
        else:
            out_dir = base_dir
        stem_base = Path(file_path).stem + suffix

        # 書き出し
        target_only: bool = data.get("target_only", False)
        stem_labels = _get_stem_labels(model_path, len(stems))
        dst_paths: list[str] = []
        for stem_idx, stem in enumerate(stems):
            if target_only and stem_idx > 0:
                continue
            if stop_event.is_set():
                return None
            stem_label = stem_labels[stem_idx] if stem_idx < len(stem_labels) else f"_stem{stem_idx + 1}"
            out_path = _unique_output_path(out_dir, stem_base + stem_label, fmt)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(out_path), stem.numpy().T, sr_target)
            dst_paths.append(str(out_path))
            _log(q, f"  → {out_path.name}")

        q.put({"type": "part", "data": {"src": file_path, "dst": dst_paths}})
        q.put({"type": "progress", "value": i + 1})

    return {"processed": len(files)}


def load_audio_44k_librosa(audio_path: str):
    import librosa

    waveform, sr = librosa.load(audio_path, sr=44100, mono=False)
    return waveform, sr
