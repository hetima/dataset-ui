"""
音楽ファイル解析 CLI タスク。
stdin から JSON（ファイルパスのリスト）を受け取り、
1ファイル処理するごとに結果を JSON 1行で stdout に出力する。

入力例:
    ["path/to/a.wav", "path/to/b.mp3"]

出力行の種類:
    {"type": "progress", "current": 1, "total": 3, "path": "..."}
    {"type": "result",   "current": 1, "total": 3, "data": {bpm, keyscale, ...}}
    {"type": "error",    "current": 1, "total": 3, "path": "...", "message": "..."}
"""
import json
import sys
import librosa
import numpy as np


MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)
KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def analyze_audio(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    # BPM
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo_val = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)  # type: ignore[index]
    bpm = int(round(tempo_val))

    # キー検出
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_avg = chroma.mean(axis=1)
    major_corrs = np.array(
        [np.corrcoef(np.roll(MAJOR_PROFILE, i), chroma_avg)[0, 1] for i in range(12)]
    )
    minor_corrs = np.array(
        [np.corrcoef(np.roll(MINOR_PROFILE, i), chroma_avg)[0, 1] for i in range(12)]
    )
    best_major_idx = major_corrs.argmax()
    best_minor_idx = minor_corrs.argmax()
    if major_corrs[best_major_idx] >= minor_corrs[best_minor_idx]:
        keyscale = f"{KEY_NAMES[best_major_idx]} major"
    else:
        keyscale = f"{KEY_NAMES[best_minor_idx]} minor"

    # 拍子推定
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    _, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
    if len(beats) >= 8:
        beat_strengths = onset_env[beats]
        acf = np.correlate(
            beat_strengths - beat_strengths.mean(),
            beat_strengths - beat_strengths.mean(),
            mode="full",
        )
        acf = acf[len(acf) // 2:]
        if len(acf) > 6:
            score_3 = acf[3] if len(acf) > 3 else 0
            score_4 = acf[4] if len(acf) > 4 else 0
            timesig = "3" if score_3 > score_4 * 1.2 else "4"
        else:
            timesig = "4"
    else:
        timesig = "4"

    del y, sr
    return {
        "path": audio_path,
        "bpm": bpm,
        "keyscale": keyscale,
        "timesignature": timesig,
        "duration": int(round(duration)),
    }


def main():
    raw = sys.stdin.read()
    paths: list[str] = json.loads(raw)
    total = len(paths)

    if total == 0:
        return

    print("[[[initial_result_start]]]", flush=True)
    print(json.dumps({"count": total}), flush=True)
    print("[[[initial_result_end]]]", flush=True)

    for i, path in enumerate(paths, start=1):
        print(f"解析中 ({i}/{total}): {path}", flush=True)
        try:
            data = analyze_audio(path)
            result = {"type": "result", "current": i, "total": total, "data": data}
            print("[[[part_result_start]]]", flush=True)
            print(json.dumps(result), flush=True)
            print("[[[part_result_end]]]", flush=True)
        except Exception as e:
            print(f"エラー: {path}: {e}", flush=True)


if __name__ == "__main__":
    main()
