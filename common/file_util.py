from pathlib import Path


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


def audio_files_in_folder(folder_path: str) -> list[Path]:
    """フォルダ内の対応音声ファイルをファイル名でソートして返す。"""
    folder = Path(folder_path)
    return audio_files_in_list(list(folder.iterdir()))
