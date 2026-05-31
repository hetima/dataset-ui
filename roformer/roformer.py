import copy
from pathlib import Path
from common.setting import cnfg
from roformer.constant import KNOWN_MODELS


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
        models.append({
            "name": path.stem,
            "path": str(path),
            "relative_path": str(path.relative_to(roformer_dir)),
            "config": str(config) if config.exists() else None,
        })
    return models


def list_known_models() -> list[dict]:
    """KNOWN_MODELS の各エントリに exists プロパティを付与して返す。"""
    roformer_dir = Path(cnfg.models_dir) / "roformer"
    result = []
    for entry in KNOWN_MODELS:
        folder = entry["repo_id"].replace("/", "--")
        model_path = roformer_dir / folder / Path(entry["filename"])
        item = copy.copy(entry)
        item["exists"] = model_path.exists()
        result.append(item)
    return result
