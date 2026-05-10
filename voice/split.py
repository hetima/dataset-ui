#
# from https://github.com/yesiampapa/rvc_split_audio/blob/main/split.py
#
import os
import multiprocessing
from functools import partial
from pydub import AudioSegment, silence

from pathlib import Path
from collections.abc import Generator

########################################
# 1) 初期無音分割
########################################
def split_into_phrases(audio: AudioSegment, min_silence_len=300, silence_thresh=-40) -> list:
    """
    無音区間(min_silence_len ms & < silence_thresh dB)を境に分割。
    """
    return silence.split_on_silence(
        audio,
        min_silence_len=min_silence_len,
        silence_thresh=silence_thresh,
        keep_silence=0,
    )


########################################
# 2) 5秒を超えるフレーズを "音量の低い部分" で分割
########################################
def find_lowest_volume_split(ch: AudioSegment, search_range_ms=1000):
    """
    チャンク中央付近 ± (search_range_ms/2) を探索し、
    RMS(平均振幅)が最小の位置を探す簡易実装。
    """
    length = len(ch)
    if length <= search_range_ms:
        return length // 2  # 中央で切る

    mid = length // 2
    start_search = max(0, mid - search_range_ms // 2)
    end_search = min(length, mid + search_range_ms // 2)

    min_rms = float("inf")
    best_pos = mid
    step = 50  # 50ms刻み
    i = start_search
    while i < end_search:
        seg = ch[i : i + step]
        if seg.rms < min_rms: # type: ignore
            min_rms = seg.rms # type: ignore
            best_pos = i + step // 2
        i += step

    return best_pos


def split_by_low_volume(ch: AudioSegment, max_sec=5, fade_ms=10, search_ms=1000):
    """
    チャンクが max_sec(秒)超なら、
    "音量の低い箇所"でフェード分割(再帰)。
    """
    max_len = max_sec * 1000
    if len(ch) <= max_len:
        return [ch]

    result = []
    remaining = ch
    while len(remaining) > max_len:
        split_pos = find_lowest_volume_split(remaining, search_ms)
        left = remaining[:split_pos].fade_out(fade_ms)
        right = remaining[split_pos:].fade_in(fade_ms)

        # leftがまだ長すぎれば再帰
        if len(left) > max_len:
            result.extend(split_by_low_volume(left, max_sec, fade_ms, search_ms))
        else:
            result.append(left)

        remaining = right
    # 最後の残り
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
                # バッファが1秒未満
                if len(buffer) + len(ch) + gap_ms <= max_sec * 1000:
                    buffer = fade_merge(buffer, ch, fade_ms, gap_ms)
                else:
                    # 合体すると 5秒超 → buffer確定
                    if len(buffer) < min_sec * 1000:
                        buffer = pad_to_length(buffer, ideal_pad_sec * 1000)
                    result.append(buffer)
                    buffer = ch
            else:
                # バッファ >=1s
                if len(buffer) + len(ch) + gap_ms <= max_sec * 1000:
                    buffer = fade_merge(buffer, ch, fade_ms, gap_ms)
                else:
                    result.append(buffer)
                    buffer = ch

    # 最後の残り
    if len(buffer) > 0:
        if len(buffer) < min_sec * 1000:
            buffer = pad_to_length(buffer, ideal_pad_sec * 1000)
        result.append(buffer)

    return result


def fade_merge(ch1: AudioSegment, ch2: AudioSegment, fade_ms=10, gap_ms=100):
    gap = AudioSegment.silent(duration=gap_ms)
    ch1_faded = ch1.fade_out(fade_ms)
    ch2_faded = ch2.fade_in(fade_ms)
    return ch1_faded + gap + ch2_faded


def pad_to_length(ch: AudioSegment, target_ms: int):
    needed = target_ms - len(ch)
    if needed > 0:
        return ch + AudioSegment.silent(duration=needed)
    return ch


########################################
# メイン処理: 1ファイル単位
########################################
def process_one_file(
    path_str: str, output_dir_str:str|None = None, min_silence_len=300, silence_thresh=-60, min_sec=1, max_sec=5, fade_ms=10, gap_ms=100, output_format="wav"
) -> list[str]:
    path = Path(path_str)
    base = path.stem
    if output_dir_str is None:
        output_dir = path.parent
    else:
        output_dir = Path(output_dir_str)
    audio = AudioSegment.from_file(path)
    files = []

    # 1) 無音区間で分割
    phrases = split_into_phrases(audio, min_silence_len, silence_thresh)

    # 2) 5秒超チャンク → 音量の低い部分で再帰的に分割
    splitted = []
    for ph in phrases:
        if len(ph) > max_sec * 1000:
            sublist = split_by_low_volume(ph, max_sec, fade_ms)
            splitted.extend(sublist)
        else:
            splitted.append(ph)

    # 3) 短いチャンク(<1s) を結合 or パディング
    final_chunks = merge_chunks(
        splitted,
        min_sec=min_sec,
        max_sec=max_sec,
        ideal_pad_sec=4,
        fade_ms=fade_ms,
        gap_ms=gap_ms,
    )

    # 4) 出力
    output_dir.mkdir(parents=True, exist_ok=True)
    for i, ch in enumerate(final_chunks, start=1):
        out_name = f"{base}_part{i:03d}.{output_format}"
        out_path = str(output_dir / out_name)
        ch.export(out_path, format=output_format)
        files.append(out_path)
    return files


def transcript_main(
    data: dict, stop_event
) -> Generator[tuple[float, str, dict | None], None, dict]:
    print("split task started...")

    files = data.get("files", [])
    output_dir = data.get("output_dir", None)
    min_sec = data.get("min_sec", 1)
    max_sec = data.get("max_sec", 5)
    output_format = data.get("format", "wav")
    if output_format not in ["wav", "mp3", "flac"]:
        output_format = "wav"

    yield 0, "処理開始", None
    cnt = len(files)
    if cnt == 0:
        yield 1, "完了", None
        return {"err": "処理するファイルがありませんでした"}

    try:
        for path in files:
            if stop_event.is_set():
                yield 1, "キャンセル", None
                return {"result": {}}
            if not output_dir:
                output_dir_str = str(Path(path).stem)
            else:
                output_dir_str = output_dir
            result = process_one_file(
                path_str=path,
                output_dir_str=output_dir_str,
                min_sec=min_sec,
                max_sec=max_sec,
                output_format=output_format,
            )
            i = i + 1
            yield i / cnt, f"処理 ({i}/{cnt})", {"result": {"src": path, "dst": result}}
        return {"result": {}}
    except Exception as e:
        yield 1, "エラー", None
        return {"err": str(e)}
    finally:
        print("...transcribe task finished")
