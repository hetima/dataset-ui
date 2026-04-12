import librosa
import numpy as np
from collections.abc import Callable, Generator

# Key profiles for Krumhansl-Schmuckler key detection
MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)
KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def analyze_main(data, stop_event) -> Generator[tuple[float, str], None, list]:
    new_data = []
    yield 0, "処理開始"
    cnt = len(data)
    if cnt == 0:
        yield 1, "完了"
        return []
    i = 0
    for path in data:
        if stop_event.is_set():
            yield 1, "キャンセル"
            return []
        # path = str(music_file.path)
        result = analyze_audio(path)
        # music_file.bpm = result.get("bpm", music_file.bpm)
        # music_file.keyscale = result.get("keyscale", music_file.keyscale)
        # music_file.timesignature = result.get("timesignature", music_file.timesignature)
        # music_file.duration = result.get("duration", music_file.duration)
        i = i + 1
        new_data.append(result)
        yield i / cnt, f"処理 ({i}/{cnt})"
    # ctx.file_grid.options["rowData"] = new_data
    return new_data


def analyze_audio(audio_path):
    """
    Extract BPM, key, and time signature from audio using librosa.
    from ai-toolkit
    """
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    # BPM
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    if hasattr(tempo, "__len__"):
        tempo = tempo[0]  # type: ignore
    bpm = int(round(float(tempo)))

    # Key detection via chroma correlation with key profiles
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

    # Time signature estimation from beat strength pattern
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo_est, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
    if len(beats) >= 8:
        beat_strengths = onset_env[beats]
        # Check 3/4 vs 4/4 by looking at periodicity of strong beats
        acf = np.correlate(
            beat_strengths - beat_strengths.mean(),
            beat_strengths - beat_strengths.mean(),
            mode="full",
        )
        acf = acf[len(acf) // 2 :]
        if len(acf) > 6:
            # Look at autocorrelation peaks at lag 3 vs lag 4
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
