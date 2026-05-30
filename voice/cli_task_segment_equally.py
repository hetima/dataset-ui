"""
均等分割 CLI タスク。
stdin から JSON を受け取り、音声ファイルを均等に分割する。

入力例:
    {
        "files": ["path/to/a.wav", ...],
        "output_dir": null,
        "overwrite": true,
        "format": "wav",
        "segment_sec": 5.0
    }

出力:
    マーカー形式で結果を stdout に出力
"""
import json
import os
import shutil
import sys
from pathlib import Path

from pydub import AudioSegment


def process_one_file(
    path_str: str, output_dir_str: str, segment_sec: float, output_format: str
) -> list[str]:
    """音声ファイルを均等に分割する"""
    path = Path(path_str)
    base = path.stem
    if output_dir_str is None:
        output_dir = path.parent
    else:
        output_dir = Path(output_dir_str)
    audio = AudioSegment.from_file(path)
    segment_ms = int(segment_sec * 1000)
    files = []

    output_dir.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(audio), segment_ms):
        segment = audio[i: i + segment_ms]
        part_num = (i // segment_ms) + 1
        out_name = f"{base}_part{part_num:03d}.{output_format}"
        out_path = str(output_dir / out_name)
        segment.export(out_path, format=output_format)  # type: ignore
        files.append(str(out_path))
    return files


def main():
    data = json.loads(sys.stdin.read())
    files: list[str] = data.get("files", [])
    output_dir_root = data.get("output_dir", None)
    overwrite: bool = data.get("overwrite", False)
    segment_sec: float = data.get("segment_sec", 5.0)
    output_format: str = data.get("format", "wav")
    if output_format not in ["wav", "mp3", "flac"]:
        output_format = "wav"

    total = len(files)
    if total == 0:
        print("処理するファイルがありませんでした", flush=True)
        return

    print("[[[initial_result_start]]]", flush=True)
    print(json.dumps({"count": total}), flush=True)
    print("[[[initial_result_end]]]", flush=True)

    for i, path in enumerate(files, start=1):
        print(f"処理中 ({i}/{total}): {path}", flush=True)
        try:
            if not output_dir_root:
                output_dir_str = str(Path(path).parent / Path(path).stem)
            else:
                output_dir_str = str(Path(output_dir_root) / Path(path).stem)

            if os.path.exists(output_dir_str):
                if overwrite and os.path.isdir(output_dir_str):
                    shutil.rmtree(output_dir_str)
                else:
                    print(f"エラー: 出力先「{output_dir_str}」はすでに存在しています", flush=True)
                    continue

            result = process_one_file(
                path_str=path,
                output_dir_str=output_dir_str,
                segment_sec=segment_sec,
                output_format=output_format,
            )
            print("[[[part_result_start]]]", flush=True)
            print(json.dumps({"data": {"src": path, "dst": result}}), flush=True)
            print("[[[part_result_end]]]", flush=True)
        except Exception as e:
            print(f"エラー: {path}: {e}", flush=True)


if __name__ == "__main__":
    main()
