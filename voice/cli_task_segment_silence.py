"""
## 元ソース
https://github.com/yesiampapa/rvc_split_audio

純正の `pydub` では問題ないが、`pozalabs-pydub` だと落ちるので修正

### 1. `split_by_low_volume` の再帰無限ループ（`RecursionError`）
再帰構造を while ループに変更し、反復上限ガードを追加。分割位置が不正の場合は等間隔分割（`_split_chunk_evenly`）にフォールバック

### 2. `find_lowest_volume_split` の最小分割サイズ未保証
`min_split_ms=500` を追加し、戻り値が両端から500ms以上を保証するよう探索範囲を制限

### 3. pydub の `fade_out`/`fade_in` で `ValueError`
短いセグメント（数ms）に対するフェード呼び出しで、内部のミリ秒→バイト変換の丸め誤差により `ValueError: invalid start_byte/end_byte range` が発生。`_safe_fade` ヘルパーで `try/except` + リトライを実装

---
無音検出分割 CLI タスク。
stdin から JSON を受け取り、音声ファイルを無音区間で分割する。

入力例:
    {
        "files": ["path/to/a.wav", ...],
        "output_dir": null,
        "overwrite": true,
        "format": "wav",
        "min_sec": 2,
        "max_sec": 5,
        "silence_thresh": -60
    }

出力:
    マーカー形式で結果を stdout に出力
"""

import json
import os
import shutil
import sys
from pathlib import Path

from pydub import AudioSegment, silence


########################################
# 1) 初期無音分割
########################################
def split_into_phrases(audio: AudioSegment, min_silence_len=300, silence_thresh=-40) -> list:
    """無音区間(min_silence_len ms & < silence_thresh dB)を境に分割。"""
    return silence.split_on_silence(
        audio,
        min_silence_len=min_silence_len,
        silence_thresh=silence_thresh,
        keep_silence=0,
    )


########################################
# 2) 5秒を超えるフレーズを "音量の低い部分" で分割
########################################
def find_lowest_volume_split(ch: AudioSegment, search_range_ms=1000, min_split_ms=500):
    """
    チャンク中央付近 ± (search_range_ms/2) を探索し、
    RMS(平均振幅)が最小の位置を探す。
    戻り値は min_split_ms <= pos <= len(ch) - min_split_ms を保証。
    """
    length = len(ch)
    if length < min_split_ms * 2:
        return length // 2

    if length <= search_range_ms:
        return length // 2

    mid = length // 2
    start_search = max(min_split_ms, mid - search_range_ms // 2)
    end_search = min(length - min_split_ms, mid + search_range_ms // 2)

    if start_search >= end_search:
        return mid

    min_rms = float("inf")
    best_pos = mid
    step = 50
    i = start_search
    while i < end_search:
        seg = ch[i: i + step]
        if seg.rms < min_rms:  # type: ignore
            min_rms = seg.rms  # type: ignore
            best_pos = i + step // 2
        i += step

    return best_pos


def _split_chunk_evenly(ch: AudioSegment, max_ms: int):
    """チャンクを max_ms 以下の等間隔に分割するフォールバック。"""
    length = len(ch)
    n = max(2, (length + max_ms - 1) // max_ms)
    chunk_size = length // n
    result = []
    for i in range(n):
        start = i * chunk_size
        end = (i + 1) * chunk_size if i < n - 1 else length
        result.append(ch[start:end])
    return result


def split_by_low_volume(ch: AudioSegment, max_sec=5, fade_ms=10, search_ms=1000):
    """
    チャンクが max_sec(秒)超なら、
    "音量の低い箇所"でフェード分割。
    再帰ではなくループで処理し、進まない場合は等間隔フォールバック。
    """
    max_len = max_sec * 1000
    if len(ch) <= max_len:
        return [ch]

    min_split_ms = 500
    result = []
    remaining = ch
    max_iterations = 10000
    iteration = 0

    while len(remaining) > max_len and iteration < max_iterations:
        iteration += 1
        split_pos = find_lowest_volume_split(remaining, search_ms, min_split_ms)

        if split_pos <= min_split_ms or split_pos >= len(remaining) - min_split_ms:
            result.extend(_split_chunk_evenly(remaining, max_len))
            return result

        left = remaining[:split_pos]
        right = remaining[split_pos:]
        fade_l = min(fade_ms, len(left) // 2) if len(left) > 0 else 0
        fade_r = min(fade_ms, len(right) // 2) if len(right) > 0 else 0
        left = _safe_fade(left, fade_l, "out")
        right = _safe_fade(right, fade_r, "in")

        result.append(left)
        remaining = right

    if len(remaining) > 0:
        result.append(remaining)
    return result


########################################
# 3) 短いチャンク(<1s) を結合 or パディング
########################################
def merge_chunks(chunks, min_sec=1, max_sec=5, ideal_pad_sec=4, fade_ms=10, gap_ms=100):
    """
    - チャンク順に走査
    - 現在バッファが <1s なら次チャンクと合体(フェード+無音)して 5s以内ならOK
    - 合体できない or 合体相手がない場合はパディング(4秒くらい)
    - バッファが >=1s の場合も、次チャンクと合体して5s以内なら続ける
    """
    result = []
    buffer = AudioSegment.empty()

    for ch in chunks:
        if len(buffer) == 0:
            buffer = ch
        else:
            if len(buffer) < min_sec * 1000:
                if len(buffer) + len(ch) + gap_ms <= max_sec * 1000:
                    buffer = fade_merge(buffer, ch, fade_ms, gap_ms)
                else:
                    if len(buffer) < min_sec * 1000:
                        buffer = pad_to_length(buffer, ideal_pad_sec * 1000)
                    result.append(buffer)
                    buffer = ch
            else:
                if len(buffer) + len(ch) + gap_ms <= max_sec * 1000:
                    buffer = fade_merge(buffer, ch, fade_ms, gap_ms)
                else:
                    result.append(buffer)
                    buffer = ch

    if len(buffer) > 0:
        if len(buffer) < min_sec * 1000:
            buffer = pad_to_length(buffer, ideal_pad_sec * 1000)
        result.append(buffer)

    return result


def _safe_fade(seg: AudioSegment, fade_ms: int, direction: str) -> AudioSegment:
    """pydubの丸め誤差による ValueError を回避するフェードヘルパー。"""
    if fade_ms <= 0 or len(seg) == 0:
        return seg
    fade_ms = min(fade_ms, len(seg))
    try:
        if direction == "out":
            return seg.fade_out(fade_ms)
        else:
            return seg.fade_in(fade_ms)
    except (ValueError, Exception):
        try:
            fade_ms = max(1, fade_ms // 2)
            if direction == "out":
                return seg.fade_out(fade_ms)
            else:
                return seg.fade_in(fade_ms)
        except (ValueError, Exception):
            return seg


def fade_merge(ch1: AudioSegment, ch2: AudioSegment, fade_ms=10, gap_ms=100):
    gap = AudioSegment.silent(duration=gap_ms)
    fade1 = min(fade_ms, len(ch1) // 2) if len(ch1) > 0 else 0
    fade2 = min(fade_ms, len(ch2) // 2) if len(ch2) > 0 else 0
    ch1_faded = _safe_fade(ch1, fade1, "out")
    ch2_faded = _safe_fade(ch2, fade2, "in")
    return ch1_faded + gap + ch2_faded


def pad_to_length(ch: AudioSegment, target_ms: int):
    needed = target_ms - len(ch)
    if needed > 0:
        return ch + AudioSegment.silent(duration=needed)
    return ch


########################################
# メイン処理: 1ファイル単位
########################################
def split_one_file(
    path_str: str, min_silence_len=300, silence_thresh=-60, min_sec=2, max_sec=5, fade_ms=10, gap_ms=100
) -> list[AudioSegment]:
    """process_one_file と同じ分割処理を行い、ファイルに書き出さず AudioSegment のリストを返す。"""
    path = Path(path_str)
    audio = AudioSegment.from_file(path)

    phrases = split_into_phrases(audio, min_silence_len, silence_thresh)

    splitted = []
    for ph in phrases:
        if len(ph) > max_sec * 1000:
            sublist = split_by_low_volume(ph, max_sec, fade_ms)
            splitted.extend(sublist)
        else:
            splitted.append(ph)

    final_chunks = merge_chunks(
        splitted,
        min_sec=min_sec,
        max_sec=max_sec,
        ideal_pad_sec=4,
        fade_ms=fade_ms,
        gap_ms=gap_ms,
    )

    # max_sec を超えるチャンクを等間隔で強制分割
    max_ms = max_sec * 1000
    enforced = []
    for ch in final_chunks:
        if len(ch) > max_ms:
            enforced.extend(_split_chunk_evenly(ch, max_ms))
        else:
            enforced.append(ch)
    return enforced


def process_one_file(
    path_str: str, output_dir_str: str | None = None, min_silence_len=300, silence_thresh=-60, min_sec=2, max_sec=5, fade_ms=10, gap_ms=100, output_format="wav"
) -> list[str]:
    path = Path(path_str)
    base = path.stem
    if output_dir_str is None:
        output_dir = path.parent
    else:
        output_dir = Path(output_dir_str)
    audio = AudioSegment.from_file(path)
    files = []

    phrases = split_into_phrases(audio, min_silence_len, silence_thresh)

    splitted = []
    for ph in phrases:
        if len(ph) > max_sec * 1000:
            sublist = split_by_low_volume(ph, max_sec, fade_ms)
            splitted.extend(sublist)
        else:
            splitted.append(ph)

    final_chunks = merge_chunks(
        splitted,
        min_sec=min_sec,
        max_sec=max_sec,
        ideal_pad_sec=4,
        fade_ms=fade_ms,
        gap_ms=gap_ms,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    for i, ch in enumerate(final_chunks, start=1):
        out_name = f"{base}_part{i:03d}.{output_format}"
        out_path = str(output_dir / out_name)
        ch.export(out_path, format=output_format)
        files.append(out_path)
    return files


def main():
    data = json.loads(sys.stdin.read())
    files: list[str] = data.get("files", [])
    output_dir_root = data.get("output_dir", None)
    overwrite: bool = data.get("overwrite", False)
    min_sec = data.get("min_sec", 2)
    max_sec = data.get("max_sec", 5)
    silence_thresh = data.get("silence_thresh", -60)
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
                min_sec=min_sec,
                max_sec=max_sec,
                silence_thresh=silence_thresh,
                output_format=output_format,
            )
            print("[[[part_result_start]]]", flush=True)
            print(json.dumps({"data": {"src": path, "dst": result}}), flush=True)
            print("[[[part_result_end]]]", flush=True)
        except Exception as e:
            print(f"エラー: {path}: {e}", flush=True)


if __name__ == "__main__":
    main()
