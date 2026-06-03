"""
タイムストレッチ CLI タスク。
stdin から JSON を受け取り、音声ファイルの速度を変更する。

from_fps を to_fps にリマップしたとき音声がどう変化するかを基準とする。
例: 25fps の動画音声を 15fps に変換 → rate = 25/15 → 音声は遅く・長くなる

入力例:
    {
        "files": ["path/to/a.wav", ...],
        "output_dir": "/path/to/output",
        "from_fps": 25.0,
        "to_fps": 15.0,
        "output_format": "wav"
    }

出力:
    マーカー形式で結果を stdout に出力
"""
import json
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


def stretch_file_librosa(path_str: str, rate: float, output_path: str, output_format: str) -> str:
    """librosa でタイムストレッチして保存する。rate > 1 で速く（短く）、rate < 1 で遅く（長く）なる"""
    y, sr = librosa.load(path_str, sr=None, mono=False)
    if y.ndim == 1:
        y_stretched = librosa.effects.time_stretch(y, rate=rate)
    else:
        # ステレオ等マルチチャンネルは各チャンネルを処理
        y_stretched = np.stack([librosa.effects.time_stretch(ch, rate=rate) for ch in y])
    sf.write(output_path, y_stretched.T if y_stretched.ndim > 1 else y_stretched, sr, format=output_format.upper())
    return output_path


def stretch_file_rubberband(path_str: str, rate: float, output_path: str, output_format: str) -> str:
    """pyrubberband でタイムストレッチして保存する。rate > 1 で速く（短く）、rate < 1 で遅く（長く）なる"""
    import pyrubberband as pyrb
    y, sr = librosa.load(path_str, sr=None, mono=False)
    if y.ndim == 1:
        y_stretched = pyrb.time_stretch(y, sr, rate)
    else:
        # pyrubberband は (samples, channels) を想定
        y_stretched = pyrb.time_stretch(y.T, sr, rate, rbargs={"-3": True}).T
    sf.write(output_path, y_stretched.T if y_stretched.ndim > 1 else y_stretched, sr, format=output_format.upper())
    return output_path


def main():
    data = json.loads(sys.stdin.read())
    files: list[str] = data.get("files", [])
    output_dir_str: str | None = data.get("output_dir", None)
    from_fps: float = float(data.get("from_fps", 1.0))
    to_fps: float = float(data.get("to_fps", 1.0))
    output_format: str = data.get("output_format", "wav")
    if output_format not in ["wav", "flac", "mp3"]:
        output_format = "wav"
    method: str = data.get("method", "librosa")

    rate = to_fps / from_fps

    total = len(files)
    if total == 0:
        print("処理するファイルがありませんでした", flush=True)
        return

    print(f"変換レート: {from_fps} → {to_fps} fps  (rate={rate:.4f})", flush=True)

    print("[[[initial_result_start]]]", flush=True)
    print(json.dumps({"count": total}), flush=True)
    print("[[[initial_result_end]]]", flush=True)

    for i, path_str in enumerate(files, start=1):
        print(f"処理中 ({i}/{total}): {path_str}", flush=True)
        try:
            path = Path(path_str)
            if output_dir_str:
                out_dir = Path(output_dir_str)
            else:
                out_dir = path.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            base_name = f"{path.stem}_ts"
            out_path = str(out_dir / f"{base_name}.{output_format}")
            counter = 1
            while Path(out_path).exists():
                out_path = str(out_dir / f"{base_name}_{counter}.{output_format}")
                counter += 1

            if method == "rubberband":
                stretch_file_rubberband(path_str, rate=rate, output_path=out_path, output_format=output_format)
            else:
                stretch_file_librosa(path_str, rate=rate, output_path=out_path, output_format=output_format)

            print("[[[part_result_start]]]", flush=True)
            print(json.dumps({"data": {"src": path_str, "dst": out_path}}), flush=True)
            print("[[[part_result_end]]]", flush=True)
        except Exception as e:
            print(f"エラー: {path_str}: {e}", flush=True)


if __name__ == "__main__":
    main()
