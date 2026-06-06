from pathlib import Path
from typing import Callable

from nicegui import binding, ui
from nicegui.elements.table import Table
from nicegui.functions.refreshable import refreshable

from common.file_util import audio_files_in_folder, Mtdt
from common.setting import cnfg
from music.musicfile import MusicFile

@binding.bindable_dataclass
class MusicCtx:
    def __init__(self):
        self.name = "dataset-ui-music"
        self.files = []
        self.folder = None
        self.table: Table
        self.save_json: bool = True
        self.save_lyrics: bool = True
        self.save_aitk: bool = False
        self.save_mtdt: bool = True
        self.target = "selected"
        self.model_refresh_func: list[Callable[[], None]] = []
        self.dataset_dirs_refresh_func: list[Callable[[], None]] = []
        self.client = ui.context.client
        self.pickup = None
        self.info_panel: refreshable

    def notify(self, text: str, type = None):
        with self.client:
            ui.notify(text, type=type)

    def load_files(self, path: str | None) -> None:
        folder_path = path
        self.pickup = None
        if hasattr(self, "info_panel"):
            self.info_panel.refresh()
        if not folder_path:
            self.notify("フォルダパスを入力してください", type="warning")
            return

        self.folder = Path(folder_path.strip())
        if not self.folder.is_dir():
            self.notify(f"フォルダが見つかりません: {folder_path}", type="negative")
            return

        cnfg.music.last_dataset_path = folder_path
        cnfg.music.add_recent_dir(folder_path)
        cnfg.save()

        mtdt_path = self.folder / "mtdt.json"
        mtdt = Mtdt(mtdt_path) if mtdt_path.exists() else None

        self.files = []
        for file in audio_files_in_folder(self.folder):
            musicfile = MusicFile.from_audio_file(file, mtdt)
            self.files.append(musicfile)

        self.table.rows = self.files
        self.table.selected = []
        self.table.update()

        if not self.files:
            self.notify("サポート対象のファイルが見つかりません")
        else:
            self.notify(f"{len(self.files)} 件のファイルを読み込みました", type="positive")

    def target_files(self) -> list:
        if self.target == "all":
            return self.files
        rows = self.table.selected
        return rows

    def music_file_for_path(self, path: str) -> MusicFile | None:
        if not path:
            return None
        return next((d for d in self.files if d.path == path), None)

    def update_file(self, data: dict) -> None:
        file = self.music_file_for_path(data.get("path", ""))
        if file is None:
            return
        for key, val in data.items():
            file[key] = val
        self.table.update()

    def analyzed(self, result_files: list) -> None:
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

    def transcripted(self, result_files: list) -> None:
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

        mtdt = None
        if self.save_mtdt and self.folder:
            mtdt_path = self.folder / "mtdt.json"
            mtdt = Mtdt(mtdt_path)

        for file in files:
            if self.save_json:
                file.save_to_json()
            if self.save_lyrics:
                file.save_to_lyrics()
            if self.save_aitk:
                file.save_to_aitk()
            if mtdt:
                mtdt.merge_song(file.name, file.to_mtdt())
        if mtdt:
            mtdt.save()
        self.notify("保存しました", type="positive")

    def set_metadata_all(self, key: str, val: str) -> None:
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
        self.notify(f"{len(targets)}件のデータを更新しました")

    def set_lang(self, val: str) -> None:
        self.set_metadata_all("language", val)

    def set_caption(self, val: str) -> None:
        self.set_metadata_all("caption", val)

    def set_models_root(self, path: str | None):
        if path and cnfg.set_models_dir(path):
            for func in self.model_refresh_func:
                func()
        self.notify("モデルパスを保存しました")

    def set_outputs_dir(self, path: str | None):
        if path and cnfg.set_outputs_dir(path):
            self.notify("書き出しパスを保存しました")

    def add_dataset_dir(self, path: str) -> bool:
        if not path or path in cnfg.music.dataset_dirs:
            return False
        if not Path(path).is_dir():
            self.notify(f"フォルダ「{path}」は存在しません", type="negative")
            return False

        if cnfg.music.add_dataset_dir(path):
            for func in self.dataset_dirs_refresh_func:
                func()
            self.notify("データセットフォルダを追加しました")
            return True
        return False

    def shift_dataset_dir(self, path: str, up: bool) -> None:
        dirs = cnfg.music.dataset_dirs
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
        if cnfg.music.delete_dataset_dir(path):
            for func in self.dataset_dirs_refresh_func:
                func()
            self.notify("データセットフォルダの登録を解除しました")
            return True
        return False

    def add_dst_to_src(self, results: list|dict) -> None:
        if isinstance(results, dict):
            results = [results]
        for result in results:
            src = result.get("src", "")
            dst_list = result.get("dst", [])
            parent_file = self.music_file_for_path(src)
            if parent_file:
                for dst in dst_list:
                    musicfile = MusicFile.from_audio_file(Path(dst))
                    parent_file.add_child(musicfile)
        self.table.update()
