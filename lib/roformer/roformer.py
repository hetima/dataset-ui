import copy
import json
from pathlib import Path
from common.setting import cnfg
from lib.roformer.constant import KNOWN_MODELS


def list_roformer_models() -> list[dict]:
    """models_dir/roformer 以下のモデルファイルを走査して返す。"""
    roformer_dir = Path(cnfg.models_dir) / "roformer"
    if not roformer_dir.is_dir():
        return []

    models = []
    for path in sorted(roformer_dir.rglob("*")):
        if path.suffix not in (".ckpt", ".safetensors"):
            continue
        config = path.with_suffix(".yaml")
        name = path.stem
        size = ""
        meta_path = path.with_suffix(".meta.json")
        output_suffix = ""
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                name = meta.get("display_name", name)
                size = meta.get("size", size)
                output_suffix = meta.get("output_suffix", "")
            except Exception:
                pass
        models.append({
            "name": name,
            "path": str(path),
            "size": size,
            "output_suffix": output_suffix,
            "relative_path": str(path.relative_to(roformer_dir)),
            "config": str(config) if config.exists() else None,
        })
    return sorted(models, key=lambda m: m["name"].lower())


def list_known_models() -> list[dict]:
    """KNOWN_MODELS の各エントリに exists プロパティを付与して返す。"""
    roformer_dir = Path(cnfg.models_dir) / "roformer"
    result = []
    for entry in KNOWN_MODELS:
        folder = entry["repo_id"].replace("/", "--")
        model_path = roformer_dir / folder / Path(entry["filename"])
        item = copy.copy(entry)
        alt_path = model_path.with_suffix(".safetensors")
        item["exists"] = model_path.exists() or alt_path.exists()
        result.append(item)
    return result
