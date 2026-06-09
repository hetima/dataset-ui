from pathlib import Path
import json

SUPPORTED_EXTENSIONS = [".flac", ".ogg", ".mp3", ".wav", ".m4a"]


def audio_files_in_list(files: list[Path]) -> list[Path]:
    """ファイルリストから対応音声ファイルをファイル名でソートして返す。

    SUPPORTED_EXTENSIONSに含まれる拡張子のファイルのみ対象。
    stemが同じファイルが複数ある場合は、拡張子の優先順位が高いもの1つだけを残す。
    """
    ext_rank = {ext: i for i, ext in enumerate(SUPPORTED_EXTENSIONS)}

    candidates: dict[str, Path] = {}
    for f in files:
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext not in ext_rank:
            continue
        stem = f.stem
        if (
            stem not in candidates
            or ext_rank[ext] < ext_rank[candidates[stem].suffix.lower()]
        ):
            candidates[stem] = f

    return [candidates[k] for k in sorted(candidates)]


def audio_files_in_folder(folder_path: str|Path) -> list[Path]:
    """フォルダ内の対応音声ファイルをファイル名でソートして返す。"""
    folder = Path(folder_path)
    return audio_files_in_list(list(folder.iterdir()))



class Mtdt:
    def __init__(self, mtdt_path: str|Path|None):
        self.mtdt_path = Path(mtdt_path) if mtdt_path else None
        # songs を {filename: data} の dict として保持（旧キー audiofiles も songs に統合して読み込む）
        self.songs: dict[str, dict] = {}
        # save() 時にファイルから削除するエントリを追跡
        self._removed: set[str] = set()
        self._load()

    def _read_raw(self) -> dict:
        """ファイルを読み込んで生の dict を返す。存在しない場合は空 dict。"""
        if not self.mtdt_path or not self.mtdt_path.exists():
            return {}
        with open(self.mtdt_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _to_store(value) -> dict[str, dict]:
        """list/dict どちらの形式も {filename: data} の dict に変換して返す。"""
        if isinstance(value, list):
            # 旧仕様: list 形式
            return {item["filename"]: item for item in value if item.get("filename")}
        if isinstance(value, dict):
            return dict(value)
        return {}

    def _load(self) -> None:
        """ファイルを読み込んで songs を構築する。旧キー audiofiles も songs に統合する。"""
        raw = self._read_raw()
        self.songs = self._to_store(raw.get("audiofiles", []))
        self.songs.update(self._to_store(raw.get("songs", [])))

    def song_data(self, filename: str) -> dict|None:
        """songs から filename に一致するエントリを返す。"""
        return self.songs.get(filename)

    def file_data(self, filename: str) -> dict|None:
        """songs から filename に一致するエントリを返す（互換用エイリアス）。"""
        return self.songs.get(filename)

    def merge_song(self, filename: str, data: dict) -> None:
        """songs の filename エントリに data をマージする（保存はしない）。"""
        if filename in self.songs:
            self.songs[filename].update(data)
        else:
            self.songs[filename] = {"filename": filename, **data}

    def merge_file(self, filename: str, data: dict) -> None:
        self.merge_song(filename, data)

    def remove_song(self, filename: str) -> None:
        """songs から filename エントリを削除する（保存はしない）。"""
        self.songs.pop(filename, None)
        self._removed.add(filename)

    def remove_file(self, filename: str) -> None:
        self.remove_song(filename)

    def save(self) -> None:
        """ファイルから再読み込みしてインスタンスデータをマージして保存する。
        songs 以外のキーや他プロセスによる変更を保持する。
        旧キー audiofiles は songs に統合してファイルから削除する。
        """
        if not self.mtdt_path:
            return
        # 現在のファイル内容をベースにする
        mtdt_all = self._read_raw()
        # 旧キー audiofiles を songs に取り込んでから songs を重ねる
        on_disk = self._to_store(mtdt_all.pop("audiofiles", []))
        on_disk.update(self._to_store(mtdt_all.get("songs", [])))
        # 削除対象を除外（取り込み後に行い、削除済みエントリが復活しないようにする）
        for filename in self._removed:
            on_disk.pop(filename, None)
        # インスタンスの変更をマージ
        for filename, data in self.songs.items():
            if filename in on_disk:
                on_disk[filename].update(data)
            else:
                on_disk[filename] = data
        # 新仕様: dict 形式で保存
        mtdt_all["songs"] = on_disk
        with open(self.mtdt_path, "w", encoding="utf-8") as f:
            json.dump(mtdt_all, f, ensure_ascii=False, indent=2)
