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
        # songs / audiofiles を {filename: data} の dict として保持
        self.songs: dict[str, dict] = {}
        self.audiofiles: dict[str, dict] = {}
        self._load()

    def _read_raw(self) -> dict:
        """ファイルを読み込んで生の dict を返す。存在しない場合は空 dict。"""
        if not self.mtdt_path or not self.mtdt_path.exists():
            return {}
        with open(self.mtdt_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load(self) -> None:
        """ファイルを読み込んで songs / audiofiles を構築する。"""
        raw = self._read_raw()
        for key in ("songs", "audiofiles"):
            store: dict[str, dict] = {}
            for item in raw.get(key, []):
                fn = item.get("filename")
                if fn:
                    store[fn] = item
            setattr(self, key, store)

    def song_data(self, filename: str) -> dict|None:
        """songs から filename に一致するエントリを返す。"""
        return self.songs.get(filename)

    def file_data(self, filename: str) -> dict|None:
        """files から filename に一致するエントリを返す。"""
        return self.audiofiles.get(filename)

    def merge_song(self, filename: str, data: dict) -> None:
        self.merge("songs", filename, data)

    def merge_file(self, filename: str, data: dict) -> None:
        self.merge("audiofiles", filename, data)

    def merge(self, key: str, filename: str, data: dict) -> None:
        """key ストアの filename エントリに data をマージする（保存はしない）。"""
        store: dict[str, dict] = getattr(self, key, {})
        if filename in store:
            store[filename].update(data)
        else:
            store[filename] = {"filename": filename, **data}

    def save(self) -> None:
        """ファイルから再読み込みしてインスタンスデータをマージして保存する。
        songs / audiofiles 以外のキーや他プロセスによる変更を保持する。
        """
        if not self.mtdt_path:
            return
        # 現在のファイル内容をベースにする
        mtdt_all = self._read_raw()
        for k in ("songs", "audiofiles"):
            entries: dict[str, dict] = getattr(self, k)
            if not entries:
                continue
            # ファイル上のリストを {filename: data} に変換
            on_disk = {item["filename"]: item for item in mtdt_all.get(k, []) if "filename" in item}
            # インスタンスの変更をマージ
            for filename, data in entries.items():
                if filename in on_disk:
                    on_disk[filename].update(data)
                else:
                    on_disk[filename] = data
            mtdt_all[k] = list(on_disk.values())
        with open(self.mtdt_path, "w", encoding="utf-8") as f:
            json.dump(mtdt_all, f, ensure_ascii=False, indent=2)
