from pathlib import Path
from typing import Any, Callable

from nicegui import binding, ui
from nicegui.elements.table import Table
from nicegui.elements.tabs import Tabs
from common.file_util import audio_files_in_folder
from common.setting import cnfg
from edit.editfile import EditFile
import send2trash

@binding.bindable_dataclass
class EditCtx:
    def __init__(self):
        self.name = "dataset-ui-music"
        self.files = []
        self.pool_files = []
        self.table: Table
        self.pool_table: Table
        self.target = "selected"
        self.model_refresh_func: list[Callable[[], None]] = []
        self.dataset_dirs_refresh_func: list[Callable[[], None]] = []
        self.daw_refresh_func: list[Callable[[], None]] = []
        self.daw_post_message_func: list[Callable[[dict[str, Any]], None]] = []
        self.daw_session_id = ""
        self.daw_url = ""
        self.client = ui.context.client
        self.tabs: Tabs

    def notify(self, text: str, type = None):
        with self.client:
            ui.notify(text, type=type)

    def update_ui(self):
        self.table.update()
        self.pool_table.update()

    def load_files(self, path: str | None) -> None:
        folder_path = path
        if not folder_path:
            self.notify("フォルダパスを入力してください", type="warning")
            return

        folder = Path(folder_path.strip())
        if not folder.is_dir():
            self.notify(f"フォルダが見つかりません: {folder_path}", type="negative")
            return

        self.files = []
        # 直下のファイル
        for file in audio_files_in_folder(folder_path):
            self.files.append(EditFile.from_audio_file(file))
        # サブフォルダ（1階層）のファイル
        for subdir in sorted(folder.iterdir()):
            if not subdir.is_dir():
                continue
            for file in audio_files_in_folder(subdir):
                editfile = EditFile.from_audio_file(file)
                editfile.name = f"{subdir.name}/{file.name}"
                self.files.append(editfile)

        self.table.rows = self.files
        self.table.selected = []
        self.update_ui()

    def load_pool(self):
        self.pool_files = [EditFile.from_audio_file(Path(f)) for f in cnfg.edit_file_paths]
        self.pool_table.rows = [f.to_dict() for f in self.pool_files]
        self.pool_table.selected = []

    def add_file(self, path: str):
        editfile = EditFile.from_audio_file(Path(path))
        self.files.append(editfile)

    def target_files(self) -> list:
        rows = self.table.selected
        poolrows = self.pool_table.selected
        return rows + poolrows

    def voice_file_for_path(self, path: str) -> EditFile | None:
        if not path:
            return None
        return next((d for d in self.files if d.path == path), None)

    def set_models_root(self, path: str | None):
        if path and cnfg.set_models_dir(path):
            for func in self.model_refresh_func:
                func()
        self.notify("モデルパスを保存しました")

    def set_outputs_dir(self, path: str | None):
        if path and cnfg.set_outputs_dir(path):
            self.notify("書き出しパスを保存しました")

    def finished(self, result_files: list) -> None:
        for voice_file in self.files:
            info = next((d for d in result_files if d["path"] == voice_file.path), None)
            if info is None:
                continue
        self.update_ui()

    def segment_finished(self, results: list) -> None:
        for result in results:
            src = result.get("src", "")
            dst_list = result.get("dst", [])
            parent_file = self.voice_file_for_path(src)
            if parent_file:
                for dst in dst_list:
                    voicefile = EditFile.from_audio_file(Path(dst))
                    parent_file.add_child(voicefile)
        self.update_ui()
    
    def update_compi(self):
        files = self.target_files()

    def delete_selected(self, permanent=False):
        rows = self.table.selected
        deleted_paths: set[str] = set()

        for row in rows:
            path = row.get("path")
            if not path:
                continue
            p = Path(path)
            try:
                if permanent:
                    if p.exists():
                        p.unlink()
                    for ext in (".txt", ".json"):
                        side = p.with_suffix(ext)
                        if side.exists():
                            side.unlink()
                else:
                    if p.exists():
                        send2trash.send2trash(path)
                    for ext in (".txt", ".json"):
                        side = p.with_suffix(ext)
                        if side.exists():
                            send2trash.send2trash(str(side))
                deleted_paths.add(path)
            except Exception as e:
                self.notify(f"ファイル「{path}」の削除に失敗しました: {e}", type="negative")

        if not deleted_paths:
            return

        deleted_names: set[str] = set()
        for f in self.files:
            if f.path in deleted_paths:
                deleted_names.add(f.name)

        self.files = [f for f in self.files if f.path not in deleted_paths]

        self.table.rows = self.files
        self.table.selected = []
        self.table.update()


