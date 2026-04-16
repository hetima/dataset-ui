from pathlib import Path
from typing import cast

from nicegui import binding, ui
from nicegui.elements.table import Table
from music.setting import cnfg
from music.musicfile import MusicFile
from music.worker import Worker

SUPPORTED_EXTENSIONS = [".wav", ".flac", ".ogg", ".mp3", ".m4a"]

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

    def load_files(self, path: str) -> None:
        folder_path = path
        if not folder_path:
            ui.notify("フォルダパスを入力してください", type="warning")
            return

        folder = Path(folder_path)
        if not folder.is_dir():
            ui.notify(f"フォルダが見つかりません: {folder_path}", type="negative")
            return

        self.files = []
        # for ext in SUPPORTED_EXTENSIONS:
        for file in sorted(folder.glob(f"*")):
            if not file.suffix in SUPPORTED_EXTENSIONS:
                continue

            musicfile = MusicFile.from_audio_file(file)
            self.files.append(musicfile.to_dict())

        if not self.files:
            ui.notify("サポート対象のファイルが見つかりません")
            return

        self.table.rows = self.files
        self.table.update()

        ui.notify(f"{len(self.files)} 件のファイルを読み込みました", type="positive")

    def target_files(self) -> list:
        if self.target == "all":
            return self.files
        rows = self.table.selected
        return rows
    
    def music_file_for_path(self, path: str) -> dict|None:
        if not path:
            return None
        return next((d for d in self.files if d["path"] == path), None)
        
    def analyzed(self, result: dict) -> None:
        result_files = result.get("result", [])
        for music_file in self.files:
            info = next((d for d in result_files if d["path"] == music_file["path"]), None)
            if info is None:
                continue
            music_file["bpm"] = info.get("bpm", music_file["bpm"])
            music_file["keyscale"] = info.get("keyscale", music_file["keyscale"])
            music_file["timesignature"] = info.get("timesignature", music_file["timesignature"])
            music_file["duration"] = info.get("duration", music_file["duration"])
        self.table.rows = self.files
        self.table.update()
    
    def transcripted(self, result: dict) -> None:
        result_files = result.get("result", [])
        for music_file in self.files:
            info = next((d for d in result_files if d["path"] == music_file["path"]), None)
            if info is None:
                continue
            music_file["lyrics"] = info.get("lyrics", music_file["lyrics"])
        self.table.rows = self.files
        self.table.update()
        
        
    def save_metadata(self) -> None:
        dicts = self.table.rows
        if len(dicts)==0:
            ui.notify("処理対象がありません")
            return
        files = [MusicFile.from_dict(item) for item in dicts]
        for file in files:
            if self.save_json:
                file.save_to_json()
            if self.save_lyrics:
                file.save_to_lyrics()
            if self.save_aitk:
                file.save_to_aitk()
        ui.notify("保存しました", type="positive")
        
    def set_metadata(self, key: str, val: str ) -> None:
        targets = self.target_files()
        if len(targets)==0:
            ui.notify("処理対象がありません")
            return
        for tgt in targets:
            result = next((item for item in self.files if item.get("name") == tgt.get("name")), None)
            if result != None:
                result[key] = val
        self.table.rows = self.files
        self.table.update()

    def set_lang(self, val: str) -> None:
        self.set_metadata("language", val)

    def set_caption(self, val: str) -> None:
        self.set_metadata("caption", val)
