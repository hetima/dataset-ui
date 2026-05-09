import dataclasses
import json
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────────────────────────────────────
REPO_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_DIR / "models"
OUTPUTS_DIR = REPO_DIR / "outputs"
SETTING_FILE = "music_config.json"
OUTPUT_PREFIX = ""

@dataclasses.dataclass
class MusicSetting:
    _EXCLUDED_SETTINGS: frozenset[str] = frozenset({
        "base_dir",
        "repo_dir",
        "setting_path",
    })

    repo_dir: Path = REPO_DIR
    base_dir: Path = BASE_DIR
    setting_path: Path = REPO_DIR / SETTING_FILE
    models_dir: Path = MODELS_DIR
    outputs_dir: Path = OUTPUTS_DIR
    output_prefix: str = OUTPUT_PREFIX
    acestep_transcriber_model: str = ""
    last_dataset_path: str = ""
    dataset_dirs: list[str] = dataclasses.field(default_factory=list)

    def __post_init__(self):
        self.load()

    def save(self):
        def _serialize(value):
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, list):
                return [_serialize(v) for v in value]
            return value

        data = {
            f.name: _serialize(getattr(self, f.name))
            for f in dataclasses.fields(self)
            if f.name not in self._EXCLUDED_SETTINGS and not f.name.startswith("_")
        }
        self.setting_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load(self):
        if not self.setting_path.exists():
            return
        data = json.loads(self.setting_path.read_text(encoding="utf-8"))
        for f in dataclasses.fields(self):
            if f.name in self._EXCLUDED_SETTINGS or f.name.startswith("_"):
                continue
            if f.name not in data:
                continue
            value = data[f.name]
            if f.type is Path:
                value = Path(value)
            setattr(self, f.name, value)
        if not self.models_dir:
            self.models_dir = MODELS_DIR

    def set_models_dir(self, path: str|Path) -> bool:
        if isinstance(path, str):
            path = path.strip()
            if path.startswith('"') and path.endswith('"'):
                path = path.strip('"')
            path = Path(path)
        if self.models_dir != path:
            self.models_dir = path
            self.save()
            return True
        return False

    def set_acestep_transcriber_model(self, name:str|None):
        if name and name != self.acestep_transcriber_model:
            self.acestep_transcriber_model = name
            self.save()

    def add_dataset_dir(self, path: str) -> bool:
        if not path or path in self.dataset_dirs:
            return False
        self.dataset_dirs.append(path)
        self.save()
        return True

    def delete_dataset_dir(self, path: str) -> bool:
        if not path or not (path in self.dataset_dirs):
            return False
        new_list = [s for s in self.dataset_dirs if s != path]
        return self.set_dataset_dir(new_list)

    def set_dataset_dir(self, new_list: list) -> bool:
        self.dataset_dirs = new_list
        self.save()
        return True


cnfg = MusicSetting()
