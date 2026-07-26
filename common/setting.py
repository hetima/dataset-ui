import dataclasses
import json
import sys
from pathlib import Path
from nicegui import binding
from common.irodori_preset import IrodoriPreset

# ─────────────────────────────────────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────────────────────────────────────
REPO_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_DIR / "models"
OUTPUTS_DIR = REPO_DIR / "outputs"
TRAIN_DIR = REPO_DIR / "train"
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
    recent_dirs: list[str] = dataclasses.field(default_factory=list)

    def save(self):
        self._root.save()

    def add_recent_dir(self, path: str) -> None:
        """最近使ったフォルダを先頭に追加し、最大8件に絞る。"""
        dirs = [d for d in self.recent_dirs if d != path]
        self.recent_dirs = [path] + dirs[:15]
        self.save()

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
    lfm_model: str = ""
    last_dataset_path: str = ""
    dataset_dirs: list[str] = dataclasses.field(default_factory=list)
    recent_dirs: list[str] = dataclasses.field(default_factory=list)
    irodori_tts_model: str = ""
    irodori_tts_output_prefix: str = "%Y-%m-%d_irodori"
    irodori_presets: list[dict] = dataclasses.field(default_factory=list)
    
    def set_irodori_tts_model(self, name: str | None):
        if name and name != self.irodori_tts_model:
            self.irodori_tts_model = name
            self.save()

    def save(self):
        self._root.save()

    def add_recent_dir(self, path: str) -> None:
        """最近使ったフォルダを先頭に追加し、最大16件に絞る。"""
        dirs = [d for d in self.recent_dirs if d != path]
        self.recent_dirs = [path] + dirs[:15]
        self.save()

    def set_asr_model(self, name: str | None):
        if name and name != self.asr_model:
            self.asr_model = name
            self.save()

    def set_lfm_model(self, name: str | None):
        if name and name != self.lfm_model:
            self.lfm_model = name
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

    def add_irodori_preset(self, preset: IrodoriPreset) -> None:
        """同名のプリセットは上書きして保存。"""
        self.irodori_presets = [p for p in self.irodori_presets if p.get("name") != preset.name]
        self.irodori_presets.append(preset.to_dict())
        self.save()

    def delete_irodori_preset(self, name: str) -> None:
        self.irodori_presets = [p for p in self.irodori_presets if p.get("name") != name]
        self.save()

@dataclasses.dataclass
class YingSubSetting:
    """ying 固有の設定。Setting._root 経由で save/load する。"""

    _root: "Setting" = dataclasses.field(default=None, init=False, repr=False) # type: ignore
    repository_dir: str = ""
    venv_dir: str = ""

    def save(self):
        self._root.save()

    def set_repository_dir(self, path: str) -> bool:
        path = path.strip().strip('"')
        if self.repository_dir == path:
            return False
        self.repository_dir = path
        self.save()
        return True

    def set_venv_dir(self, path: str) -> bool:
        path = path.strip().strip('"')
        if self.venv_dir == path:
            return False
        self.venv_dir = path
        self.save()
        return True


# ─────────────────────────────────────────────────────────────────────────────
# ルート設定クラス
# ─────────────────────────────────────────────────────────────────────────────
@binding.bindable_dataclass
class Setting:
    _EXCLUDED_SETTINGS: frozenset[str] = frozenset({
        "base_dir",
        "repo_dir",
        "setting_path",
        "python_path",
    })

    repo_dir: Path = REPO_DIR
    base_dir: Path = BASE_DIR
    setting_path: Path = REPO_DIR / SETTING_FILE
    python_path: str = dataclasses.field(default_factory=lambda: sys.executable)
    models_dir: Path = MODELS_DIR
    outputs_dir: Path = OUTPUTS_DIR
    train_dir: Path = TRAIN_DIR
    output_prefix: str = ""
    hf_token: str = ""
    edit_file_paths: list[str] = dataclasses.field(default_factory=list)

    music: MusicSubSetting = dataclasses.field(default_factory=MusicSubSetting)
    voice: VoiceSubSetting = dataclasses.field(default_factory=VoiceSubSetting)
    ying: YingSubSetting = dataclasses.field(default_factory=YingSubSetting)

    def __post_init__(self):
        # サブ設定に自身の参照を渡す
        self.music._root = self
        self.voice._root = self
        self.ying._root = self
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
            elif isinstance(value, YingSubSetting):
                data["ying"] = {
                    sf.name: _serialize(getattr(value, sf.name))
                    for sf in dataclasses.fields(value)
                    if not sf.name.startswith("_")
                }
            else:
                data[f.name] = _serialize(value)

        data["python_path"] = sys.executable

        self.setting_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load(self):
        if not self.setting_path.exists():
            self.save()
            return
        data = json.loads(self.setting_path.read_text(encoding="utf-8"))
        needs_save = False
        prev_python_path = data.get("python_path", "")
        if self.python_path != prev_python_path:
            needs_save = True
        # ルート直下フィールド
        for f in dataclasses.fields(self):
            if f.name in self._EXCLUDED_SETTINGS or f.name.startswith("_"):
                continue
            if f.name in ("music", "voice", "ying"):
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

        # ying サブ
        ying_data = data.get("ying", {})
        for f in dataclasses.fields(self.ying):
            if f.name.startswith("_"):
                continue
            if f.name not in ying_data:
                continue
            setattr(self.ying, f.name, ying_data[f.name])

        if not self.models_dir:
            self.models_dir = MODELS_DIR
        if not self.train_dir:
            self.train_dir = TRAIN_DIR
        if needs_save:
            self.save()


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

    def set_train_dir(self, path: str | Path) -> bool:
        if isinstance(path, str):
            path = path.strip()
            if path.startswith('"') and path.endswith('"'):
                path = path.strip('"')
            path = Path(path)
        if self.train_dir != path:
            self.train_dir = path
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

    @property
    def has_edit_files(self) -> bool:
        return bool(self.edit_file_paths)

    def clear_edit_file_paths(self) -> None:
        self.edit_file_paths = []
        self.save()

    def add_edit_file_path(self, path: str) -> bool:
        if not path or path in self.edit_file_paths:
            return False
        self.edit_file_paths = self.edit_file_paths + [path]
        self.save()
        return True

    def remove_edit_file_path(self, path: str) -> bool:
        if not path or path not in self.edit_file_paths:
            return False
        self.edit_file_paths = [p for p in self.edit_file_paths if p != path]
        self.save()
        return True


cnfg = Setting()
