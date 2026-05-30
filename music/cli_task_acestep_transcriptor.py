"""
ACE-Step Transcriptor CLI タスク。
stdin から JSON を受け取り、歌詞トランスクリプションを実行する。

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


class AcestepTranscriptorPipeline:
    def __init__(self, model, processor):
        self.model = model
        self.processor = processor

    def run_qwen_audio(self, audio_data, sr, prompt_text):
        """Qwen2.5-Omni モデルで音声をテキストに変換する"""
        import logging
        logging.disable(logging.WARNING)

        conversation = [
            {
                "role": "user",
                "content": [
                    {"type": "audio", "audio": "<|audio_bos|><|AUDIO|><|audio_eos|>"},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]
        text = self.processor.apply_chat_template(
            conversation, add_generation_prompt=True, tokenize=False
        )
        inputs = self.processor(
            text=text,
            audio=[audio_data],
            images=None,
            videos=None,
            return_tensors="pt",
            padding=True,
            sampling_rate=sr,
        )
        inputs = inputs.to(self.model.device).to(self.model.dtype)
        text_ids = self.model.generate(**inputs, return_audio=False)
        output = self.processor.batch_decode(
            text_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        result = output[0]
        marker = "assistant\n"
        if marker in result:
            result = result[result.rfind(marker) + len(marker):]
        return result.strip()

    @classmethod
    def from_pretrained(cls, model_path: str, device, dtype):
        from transformers import Qwen2_5OmniForConditionalGeneration, Qwen2_5OmniProcessor

        local_files_only = True
        if not os.path.exists(model_path):
            if model_path.find("/") >= 1:
                local_files_only = False
            else:
                raise FileNotFoundError(f"「{model_path}」が存在しません")
        print(f"model path: {model_path}", flush=True)
        model = Qwen2_5OmniForConditionalGeneration.from_pretrained(
            model_path, torch_dtype=dtype, device_map=device, local_files_only=local_files_only
        )
        model.disable_talker()
        processor = Qwen2_5OmniProcessor.from_pretrained(
            model_path, local_files_only=local_files_only
        )
        return cls(model=model, processor=processor)


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
        lyrics = pipe.run_qwen_audio(
            audio_data, sr, "*Task* Transcribe this audio in detail"
        )
    except Exception as e:
        print(f"\n  Error transcribing {os.path.basename(audio_path)}: {e}", flush=True)
        lyrics = "[Instrumental]"
    finally:
        del audio_data

    torch.cuda.empty_cache()
    return {
        "path": audio_path,
        "lyrics": lyrics,
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
        pipe = AcestepTranscriptorPipeline.from_pretrained(
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
