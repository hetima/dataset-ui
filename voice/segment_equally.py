import os
import shutil
from pathlib import Path
from collections.abc import Generator
from pydub import AudioSegment


def process_one_file(
    path_str: str, output_dir_str: str, segment_sec: float, output_format: str
) -> list[str]:
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
        segment = audio[i : i + segment_ms]
        part_num = (i // segment_ms) + 1
        out_name = f"{base}_part{part_num:03d}.{output_format}"
        out_path = str(output_dir / out_name)
        segment.export(out_path, format=output_format) # type: ignore
        files.append(str(out_path))
    return files


def segment_equally_main(
    data: dict, stop_event
) -> Generator[tuple[float, str, dict | None], None, dict]:
    """
    音声ファイルを均等に分割する処理のジェネレーター関数です。
    Args:
        data (dict): 処理に必要なデータを含む辞書。以下のキーを含む必要があります。
            - "input_path" (str): 分割対象の音声ファイルのパス。
            - "segment_sec" (float): 分割後の各セグメントの長さ（秒単位）。
            - "output_format" (str): 出力ファイルの形式（例: "wav", "mp3"）。
        stop_event: 処理を停止するためのイベントオブジェクト。
    """

    print("segment silence task started...")

    files = data.get("files", [])
    output_dir = data.get("output_dir", None)
    overwrite = data.get("overwrite", False)
    segment_sec = data.get("segment_sec", 5)
    output_format = data.get("format", "wav")
    if output_format not in ["wav", "mp3", "flac"]:
        output_format = "wav"

    yield 0, "処理開始", None
    cnt = len(files)
    if cnt == 0:
        yield 1, "完了", None
        return {"err": "処理するファイルがありませんでした"}

    try:
        for i, path in enumerate(files, start=1):
            print(f"processing: {path}")
            if stop_event.is_set():
                yield 1, "キャンセル", None
                return {"result": {}}
            if not output_dir:
                parent = Path(path).parent
                output_dir_str = str(parent / Path(path).stem)
            else:
                output_dir_str = output_dir

            if os.path.exists(output_dir_str):
                if overwrite and os.path.isdir(output_dir_str):
                    shutil.rmtree(output_dir_str)
                else:
                    yield 1, "エラー", None
                    return {
                        "err": f"出力先の「{output_dir_str}」はすでに存在しています"
                    }
            result = process_one_file(
                path_str=path,
                output_dir_str=output_dir_str,
                segment_sec=segment_sec,
                output_format=output_format,
            )
            yield i / cnt, f"処理 ({i}/{cnt})", {
                "result": [{"src": path, "dst": result}]
            }
        return {"result": {}}
    except Exception as e:
        yield 1, "エラー", None
        return {"err": str(e)}
    finally:
        print("...segment silence task finished")
