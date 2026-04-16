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
class Setting:
    _SAVABLE_SETTINGS: tuple[str, ...] = dataclasses.field(
        default=(
            "models_dir",
            "outputs_dir",
            "acestep_transcriber_model",
        ),
        init=False,
        repr=False,
    )

    repo_dir: Path = REPO_DIR
    base_dir: Path = BASE_DIR
    setting_path: Path = REPO_DIR / SETTING_FILE
    models_dir: Path = MODELS_DIR
    outputs_dir: Path = OUTPUTS_DIR
    output_prefix: str = OUTPUT_PREFIX
    acestep_transcriber_model: str = ""


    def __post_init__(self):
        self.load()

    def save(self):
        def _serialize(value):
            if isinstance(value, Path):
                return str(value)
            if isinstance(value, list):
                return [_serialize(v) for v in value]
            return value

        data = {name: _serialize(getattr(self, name)) for name in self._SAVABLE_SETTINGS}
        self.setting_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load(self):
        if not self.setting_path.exists():
            return
        data = json.loads(self.setting_path.read_text(encoding="utf-8"))
        for name in self._SAVABLE_SETTINGS:
            if name not in data:
                continue
            value = data[name]
            field_type = None
            for f in dataclasses.fields(self):
                if f.name == name:
                    field_type = f.type
                    break
            if field_type is Path:
                value = Path(value)
            setattr(self, name, value)

    def set_models_dir(self, path: str|Path):
        if isinstance(path, str):
            path = path.strip()
            if path.startswith('"') and path.endswith('"'):
                path = path.strip('"')
            path = Path(path)
        self.models_dir = path
        self.save()
    
    def set_acestep_transcriber_model(self, name:str|None):
        if name:
            self.acestep_transcriber_model = name
            cnfg.save()


cnfg = Setting()
cnfg.load()
