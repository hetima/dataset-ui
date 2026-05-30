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
SETTING_FILE = "config.json"


# ─────────────────────────────────────────────────────────────────────────────
# サブ設定クラス
# ─────────────────────────────────────────────────────────────────────────────
def _serialize(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


@dataclasses.dataclass
class MusicSubSetting:
    """music 固有の設定。Setting._root 経由で save/load する。"""

    _root: "Setting" = dataclasses.field(default=None, init=False, repr=False) # type: ignore

    acestep_transcriber_model: str = ""
    last_dataset_path: str = ""
    dataset_dirs: list[str] = dataclasses.field(default_factory=list)

    def save(self):
        self._root.save()

    def set_acestep_transcriber_model(self, name: str | None):
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
        if not path or path not in self.dataset_dirs:
            return False
        new_list = [s for s in self.dataset_dirs if s != path]
        return self.set_dataset_dir(new_list)

    def set_dataset_dir(self, new_list: list) -> bool:
        self.dataset_dirs = new_list
        self.save()
        return True


@dataclasses.dataclass
class VoiceSubSetting:
    """voice 固有の設定。Setting._root 経由で save/load する。"""

    _root: "Setting" = dataclasses.field(default=None, init=False, repr=False) # type: ignore

    asr_model: str = ""
    last_dataset_path: str = ""
    dataset_dirs: list[str] = dataclasses.field(default_factory=list)

    def save(self):
        self._root.save()

    def set_asr_model(self, name: str | None):
        if name and name != self.asr_model:
            self.asr_model = name
            self.save()

    def add_dataset_dir(self, path: str) -> bool:
        if not path or path in self.dataset_dirs:
            return False
        self.dataset_dirs.append(path)
        self.save()
        return True

    def delete_dataset_dir(self, path: str) -> bool:
        if not path or path not in self.dataset_dirs:
            return False
        new_list = [s for s in self.dataset_dirs if s != path]
        return self.set_dataset_dir(new_list)

    def set_dataset_dir(self, new_list: list) -> bool:
        self.dataset_dirs = new_list
        self.save()
        return True


# ─────────────────────────────────────────────────────────────────────────────
# ルート設定クラス
# ─────────────────────────────────────────────────────────────────────────────
@dataclasses.dataclass
class Setting:
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
    output_prefix: str = ""

    music: MusicSubSetting = dataclasses.field(default_factory=MusicSubSetting)
    voice: VoiceSubSetting = dataclasses.field(default_factory=VoiceSubSetting)

    def __post_init__(self):
        # サブ設定に自身の参照を渡す
        self.music._root = self
        self.voice._root = self
        self.load()

    # ── save / load ─────────────────────────────────────────────────────────

    def save(self):
        data = {}
        for f in dataclasses.fields(self):
            if f.name in self._EXCLUDED_SETTINGS or f.name.startswith("_"):
                continue
            value = getattr(self, f.name)
            if isinstance(value, MusicSubSetting):
                data["music"] = {
                    sf.name: _serialize(getattr(value, sf.name))
                    for sf in dataclasses.fields(value)
                    if not sf.name.startswith("_")
                }
            elif isinstance(value, VoiceSubSetting):
                data["voice"] = {
                    sf.name: _serialize(getattr(value, sf.name))
                    for sf in dataclasses.fields(value)
                    if not sf.name.startswith("_")
                }
            else:
                data[f.name] = _serialize(value)

        self.setting_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load(self):
        if not self.setting_path.exists():
            return
        data = json.loads(self.setting_path.read_text(encoding="utf-8"))

        # ルート直下フィールド
        for f in dataclasses.fields(self):
            if f.name in self._EXCLUDED_SETTINGS or f.name.startswith("_"):
                continue
            if f.name in ("music", "voice"):
                continue
            if f.name not in data:
                continue
            value = data[f.name]
            if f.type is Path:
                value = Path(value)
            setattr(self, f.name, value)

        # music サブ
        music_data = data.get("music", {})
        for f in dataclasses.fields(self.music):
            if f.name.startswith("_"):
                continue
            if f.name not in music_data:
                continue
            setattr(self.music, f.name, music_data[f.name])

        # voice サブ
        voice_data = data.get("voice", {})
        for f in dataclasses.fields(self.voice):
            if f.name.startswith("_"):
                continue
            if f.name not in voice_data:
                continue
            setattr(self.voice, f.name, voice_data[f.name])

        if not self.models_dir:
            self.models_dir = MODELS_DIR

    # ── setter ──────────────────────────────────────────────────────────────

    def set_models_dir(self, path: str | Path) -> bool:
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

    def set_outputs_dir(self, path: str | Path) -> bool:
        if isinstance(path, str):
            path = path.strip()
            if path.startswith('"') and path.endswith('"'):
                path = path.strip('"')
            path = Path(path)
        if self.outputs_dir != path:
            self.outputs_dir = path
            self.save()
            return True
        return False


cnfg = Setting()
