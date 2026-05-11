# dataset-ui — Agent Guidelines

## Project Overview

Web-based audio dataset metadata editor built with **NiceGUI** (Python). Two main modules:
- **music/** — Music metadata (lyrics, BPM, key, language) + ACE-Step transcription & analysis
- **voice/** — Voice metadata (transcript) + Qwen3-ASR + audio segmentation

## Run

```bash
python app.py [--host 127.0.0.1] [--port 7869] [--native] [--auto-reload]
```

## Architecture

```
app.py → NiceGUI pages (/music, /voice)
├── {module}/index.py       → tab layout (main_tab + setting_tab)
├── {module}/{module}_app_ctx.py → @binding.bindable_dataclass state container
├── {module}/{module}_main_tab.py  → processing UI + action buttons
├── {module}/{module}_setting_tab.py → model & dataset folder config
├── {module}/{module}file.py       → dataclass with dict-like access
└── common/worker.py       → multiprocessing background task executor
```

## Key Patterns

### Worker/Generator Contract
Background tasks must be generator functions yielding `(progress: float, status: str, partial_result: dict | None)` and returning a final dict. Check `stop_event.is_set()` for cancellation.

```python
def task(data, stop_event):
    yield 0.0, "開始", None
    for i, item in enumerate(items):
        if stop_event.is_set():
            return {}
        yield (i+1)/len(items), f"処理中 {i+1}/{len(items)}", None
    return final_results
```

### File Dataclasses
`MusicFile` / `VoiceFile` support both attribute and dict access (`file["path"]` ↔ `file.path`). Use `.to_dict()` / `.from_dict()` for serialization. Never access internal `_data` directly.

### Context (Ctx) Pattern
`MusicCtx` / `VoiceCtx` are `@binding.bindable_dataclass` — bind UI elements to their fields. Callback lists (`model_refresh_func`, `dataset_dirs_refresh_func`) notify UI of config changes.

## Conventions

- **Language**: UI text and comments are in **Japanese**. Maintain this convention.
- **Config**: All settings stored in `config.json` at project root. Access via `common/setting.py` — never read/write config directly.
- **Models**: Downloaded to `models_dir` (configured in `config.json`). Reference by subfolder name, not full path.
- **Audio formats**: Support `.wav`, `.flac`, `.mp3`, `.m4a`, `.ogg`, `.aac` — check `voicefile.py` / `musicfile.py` for current list.
- **CSS classes**: Use NiceGUI's `classes()` and `style()` chaining. Global styles defined in `app.py` `header()`.

## Directory Layout Notes

| Path | Purpose |
|------|---------|
| `qwen_asr/` | Qwen3-ASR integration (install with `--no-deps`) |
| `roformer/` | MelBandRoFormer audio source separation models |
| `cli/` | Standalone CLI tools (HF model downloading) |
| `var/` | Experimental/utility scripts — not part of main app |
