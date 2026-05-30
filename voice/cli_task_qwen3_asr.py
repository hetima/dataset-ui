"""
Qwen3-ASR 音声認識 CLI タスク。
stdin から JSON を受け取り、音声ファイルを文字起こしする。

入力例:
    {"model_path": "path/to/model", "files": ["path/to/a.wav", ...]}

出力:
    マーカー形式で結果を stdout に出力
"""
import gc
import json
import os
import sys


TARGET_SAMPLE_RATE = 16000
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

class QwenASRPipeline:
    def __init__(self, model):
        self.model = model

    def run_qwen_audio(self, audio_data, sr):
        """Qwen3-ASR モデルで音声を文字起こしする"""
        import logging
        logging.disable(logging.WARNING)

        results = self.model.transcribe(
            audio=(audio_data, sr),
            language="Japanese",
        )
        return results[0].text.strip()

    @classmethod
    def from_pretrained(cls, model_path: str, device, dtype):
        import torch
        from qwen_asr import Qwen3ASRModel

        local_files_only = True
        if not os.path.exists(model_path):
            if model_path.find("/") >= 1:
                local_files_only = False
            else:
                raise FileNotFoundError(f"「{model_path}」が存在しません")
        print(f"model path: {model_path}", flush=True)
        model = Qwen3ASRModel.from_pretrained(
            model_path,
            dtype=torch.bfloat16,
            device_map="cuda:0",
            max_inference_batch_size=1,
            max_new_tokens=256,
        )
        return cls(model=model)


def load_audio_mono_16k_torchaudio(audio_path: str):
    import torchaudio

    waveform, sr = torchaudio.load(audio_path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sr != TARGET_SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sr, TARGET_SAMPLE_RATE)
    return waveform.squeeze(0).numpy(), TARGET_SAMPLE_RATE


def load_audio_mono_16k_librosa(audio_path: str):
    import librosa
    waveform, _ = librosa.load(audio_path, sr=16000, mono=True)
    return waveform, 16000


def load_audio_mono_16k_pydub(audio_path: str):
    import numpy as np
    from pydub import AudioSegment

    audio = AudioSegment.from_file(audio_path).set_channels(1).set_frame_rate(16000)
    samples = np.array(audio.get_array_of_samples())
    if audio.sample_width == 2:
        samples = samples.astype(np.float32) / 32768.0
    elif audio.sample_width == 4:
        samples = samples.astype(np.float32) / 2147483648.0
    return samples


def analyze_audio(pipe, audio_path: str) -> dict:
    import torch
    try:
        print(audio_path, flush=True)
        audio_data, sr = load_audio_mono_16k_librosa(audio_path)
        transcript = pipe.run_qwen_audio(audio_data, sr)
    except Exception as e:
        print(f"\n  Error transcribing {os.path.basename(audio_path)}: {e}", flush=True)
        transcript = ""
    finally:
        del audio_data

    torch.cuda.empty_cache()
    return {
        "path": audio_path,
        "transcript": transcript,
    }


def main():
    import torch

    data = json.loads(sys.stdin.read())
    model_path: str = data["model_path"]
    files: list[str] = data.get("files", [])
    total = len(files)

    if total == 0:
        print("処理するファイルがありませんでした", flush=True)
        return

    print("[[[initial_result_start]]]", flush=True)
    print(json.dumps({"count": total}), flush=True)
    print("[[[initial_result_end]]]", flush=True)

    print("モデルを読み込んでいます...", flush=True)
    try:
        pipe = QwenASRPipeline.from_pretrained(
            model_path,
            device=torch.device("cuda"),
            dtype=torch.float16,
        )
    except FileNotFoundError as e:
        print(f"エラー: {e}", flush=True)
        return
    if pipe.model is None:
        print("エラー: モデルを読み込めませんでした", flush=True)
        return

    try:
        for i, path in enumerate(files, start=1):
            print(f"処理中 ({i}/{total}): {path}", flush=True)
            try:
                result = analyze_audio(pipe, path)
                print("[[[part_result_start]]]", flush=True)
                print(json.dumps({"data": result}), flush=True)
                print("[[[part_result_end]]]", flush=True)
            except Exception as e:
                print(f"エラー: {path}: {e}", flush=True)
    finally:
        del pipe
        gc.collect()
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
