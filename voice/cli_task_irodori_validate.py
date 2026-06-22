"""irodori-tts 用データセット候補フォルダのメタデータ状況を表示する。

stdin: JSON（データセットフォルダパスのリスト）
stdout: 検証結果のテキスト
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.file_util import Mtdt, audio_files_in_folder
from voice.voicefile import VoiceFile


def has_value(value: str | None) -> bool:
    """文字列メタデータが設定済みか判定する。"""
    return bool(value and value.strip())


def validate_folder(path: Path, *, good_only: bool = False, exclude_bad: bool = False) -> None:
    """1つのフォルダ内の音声ファイルとメタデータ件数を表示する。"""
    print(path, flush=True)
    if not path.is_dir():
        print("フォルダが見つかりません", flush=True)
        print("", flush=True)
        return

    mtdt_path = path / "mtdt.json"
    mtdt = Mtdt(mtdt_path) if mtdt_path.exists() else None
    files = [VoiceFile.from_audio_file(file, mtdt) for file in audio_files_in_folder(path)]
    if good_only:
        files = [f for f in files if f.good]
    if exclude_bad:
        files = [f for f in files if not f.bad]

    transcript_count = sum(1 for file in files if has_value(file.transcript))
    caption_count = sum(1 for file in files if has_value(file.caption))
    speaker_id_count = sum(1 for file in files if has_value(file.speaker_id))

    print(
        f"ファイル数: {len(files)}件 "
        f"transcript付き:{transcript_count}件 "
        f"caption付き:{caption_count}件 "
        f"speaker_id付き:{speaker_id_count}件",
        flush=True,
    )
    print("", flush=True)


def main() -> None:
    """stdin から受け取ったフォルダリストを順に検証する。"""
    data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    if isinstance(data, list):
        paths = data
        good_only = False
        exclude_bad = False
    else:
        paths = data["paths"]
        good_only = data.get("good_only", False)
        exclude_bad = data.get("exclude_bad", False)
    print("オーディファイルに設定されているメタデータを検証します", flush=True)
    print("transcriptはすべてのファイルに必須です。他のプロパティはオプションです", flush=True)
    if good_only:
        print("good=True のファイルのみを対象とします", flush=True)
    if exclude_bad:
        print("bad=True のファイルを除外します", flush=True)
    print("", flush=True)

    for path in paths:
        validate_folder(Path(path), good_only=good_only, exclude_bad=exclude_bad)


if __name__ == "__main__":
    main()
