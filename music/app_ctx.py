from pathlib import Path
from typing import Callable

from nicegui import binding, ui
from nicegui.elements.table import Table

from common.file_util import audio_files_in_folder
from music.setting import cnfg
from music.musicfile import MusicFile
from common.worker import Worker


@binding.bindable_dataclass
class MusicCtx:
    def __init__(self, worker: Worker):
        self.name = "dataset-ui-music"
        self.files = []
        self.table: Table
        self.save_json: bool = True
        self.save_lyrics: bool = True
        self.save_aitk: bool = False
        self.worker: Worker = worker
        self.target = "all"
        self.model_refresh_func: list[Callable[[], None]] = []
        self.dataset_dirs_refresh_func: list[Callable[[], None]] = []
        self.client = ui.context.client

    def notify(self, text: str, type = None):
        with self.client:
            ui.notify(text, type=type)

    def load_files(self, path: str) -> None:
        folder_path = path
        if not folder_path:
            self.notify("フォルダパスを入力してください", type="warning")
            return

        folder = Path(folder_path)
        if not folder.is_dir():
            self.notify(f"フォルダが見つかりません: {folder_path}", type="negative")
            return

        cnfg.last_dataset_path = folder_path
        cnfg.save()

        self.files = []
        for file in audio_files_in_folder(folder_path):
            musicfile = MusicFile.from_audio_file(file)
            self.files.append(musicfile)

        if not self.files:
            self.notify("サポート対象のファイルが見つかりません")
            return

        self.table.rows = self.files
        self.table.update()

        self.notify(f"{len(self.files)} 件のファイルを読み込みました", type="positive")

    def target_files(self) -> list:
        if self.target == "all":
            return self.files
        rows = self.table.selected
        return rows

    def music_file_for_path(self, path: str) -> dict | None:
        if not path:
            return None
        return next((d for d in self.files if d["path"] == path), None)

    def analyzed(self, result: dict) -> None:
        result_files = result.get("result", [])
        for music_file in self.files:
            info = next((d for d in result_files if d["path"] == music_file.path), None)
            if info is None:
                continue
            music_file.bpm = info.get("bpm", music_file.bpm)
            music_file.keyscale = info.get("keyscale", music_file.keyscale)
            music_file.timesignature = info.get(
                "timesignature", music_file.timesignature
            )
            music_file.duration = info.get("duration", music_file.duration)
        # self.table.rows = self.files
        self.table.update()

    def transcripted(self, result: dict) -> None:
        result_files = result.get("result", [])
        for music_file in self.files:
            info = next((d for d in result_files if d["path"] == music_file.path), None)
            if info is None:
                continue
            music_file.lyrics = info.get("lyrics", music_file.lyrics)
        # self.table.rows = self.files
        self.table.update()

    def save_metadata(self) -> None:
        files = self.files
        if len(files) == 0:
            self.notify("処理対象がありません")
            return
        # files = [MusicFile.from_dict(item) for item in dicts]
        for file in files:
            if self.save_json:
                file.save_to_json()
            if self.save_lyrics:
                file.save_to_lyrics()
            if self.save_aitk:
                file.save_to_aitk()
        self.notify("保存しました", type="positive")

    def set_metadata(self, key: str, val: str) -> None:
        targets = self.target_files()
        if len(targets) == 0:
            self.notify("処理対象がありません")
            return
        for tgt in targets:
            result = next(
                (item for item in self.files if item.get("name") == tgt.get("name")),
                None,
            )
            if result != None:
                result[key] = val
        # self.table.rows = self.files
        self.table.update()

    def set_lang(self, val: str) -> None:
        self.set_metadata("language", val)

    def set_caption(self, val: str) -> None:
        self.set_metadata("caption", val)

    def set_models_root(self, path: str):
        if cnfg.set_models_dir(path):
            for func in self.model_refresh_func:
                func()
        self.notify("モデルパスを保存しました")

    def add_dataset_dir(self, path: str) -> bool:
        if not path or path in cnfg.dataset_dirs:
            return False
        if not Path(path).is_dir():
            self.notify(f"フォルダ「{path}」は存在しません", type="negative")
            return False

        if cnfg.add_dataset_dir(path):
            for func in self.dataset_dirs_refresh_func:
                func()
            self.notify("データセットフォルダを追加しました")
            return True
        return False

    def shift_dataset_dir(self, path: str, up: bool) -> None:
        dirs = cnfg.dataset_dirs
        idx = dirs.index(path) if path in dirs else -1
        if idx < 0:
            return
        target_idx = idx - 1 if up else idx + 1
        if target_idx < 0 or target_idx >= len(dirs):
            return
        dirs[idx], dirs[target_idx] = dirs[target_idx], dirs[idx]
        cnfg.save()
        for func in self.dataset_dirs_refresh_func:
            func()

    def delete_dataset_dir(self, path: str) -> bool:
        if cnfg.delete_dataset_dir(path):
            for func in self.dataset_dirs_refresh_func:
                func()
            self.notify("データセットフォルダの登録を解除しました")
            return True
        return False
