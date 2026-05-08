import os
import gc
from pathlib import Path
from collections.abc import Generator
from voice.voice_setting import cnfg

TARGET_SAMPLE_RATE = 16000


def asr_models() -> list[str]:
    models_dir = cnfg.models_dir
    if not models_dir.exists():
        return []
    return [
        p.name
        for p in models_dir.iterdir()
        if p.is_dir()
        and "asr" in p.name.lower()
        and "qwen" in p.name.lower()
    ]


class QwenASRPipeline:
    def __init__(self, model):
        self.model = model

    def run_qwen_audio(self, audio_data, sr):
        """Run a Qwen2.5-Omni model on audio with a text prompt."""
        import logging
        logging.disable(logging.WARNING) 

        results = self.model.transcribe(
            audio=(audio_data, sr),
            language="Japanese",  # set "English" to force the language
        )
        return results[0].text.strip()

    @classmethod
    def from_pretrained(cls, device, dtype):
        import torch
        from qwen_asr import Qwen3ASRModel
        from transformers import AutoConfig, AutoModel

        local_files_only = True
        model_path = str(cnfg.models_dir / cnfg.asr_model)
        if not os.path.exists(model_path):
            if cnfg.asr_model.find("/") >= 1:
                model_path = cnfg.asr_model
                local_files_only = False
            else:
                raise FileNotFoundError(
                    f"モデルパス「  {str(cnfg.models_dir)}」 に「{cnfg.asr_model}」フォルダが存在しません"
                )
        print(f"model path: {model_path}")
        # config = AutoConfig.from_pretrained(model_path, trust_remote_code=True)
        model = Qwen3ASRModel.from_pretrained(
            model_path,
            dtype=torch.bfloat16,
            device_map="cuda:0",
            # attn_implementation="flash_attention_2",
            max_inference_batch_size=1,  # Batch size limit for inference. -1 means unlimited. Smaller values can help avoid OOM.
            max_new_tokens=256,  # Maximum number of tokens to generate. Set a larger value for long audio input.
        )

        return cls(
            model=model,
        )


def transcript_main(
    data: list[str], stop_event
) -> Generator[tuple[float, str, dict | None], None, dict]:
    import torch

    print("transcribe task started...")
    cnfg.load()
    new_data = []
    yield 0, "処理開始", None
    cnt = len(data)
    if cnt == 0:
        yield 1, "完了", None
        return {"err": "処理するファイルがありませんでした"}
    try:
        pipe = QwenASRPipeline.from_pretrained(
            device=torch.device("cuda"),
            dtype=torch.float16,
        )
    except FileNotFoundError as e:
        yield 1, "エラー", None
        return {"err": e}
    if pipe.model is None:
        yield 1, "エラー", None
        return {"err": "モデルを読み込めませんでした"}
    i = 0
    try:
        for path in data:
            if stop_event.is_set():
                yield 1, "キャンセル", None
                return {"result": []}
            result = analyze_audio(pipe, path)
            i = i + 1
            new_data.append(result)
            yield i / cnt, f"処理 ({i}/{cnt})", {"result": [result]}
        return {"result": []}
    finally:
        print("...transcribe task finished")
        del pipe
        gc.collect()
        torch.cuda.empty_cache()


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

    if audio.sample_width == 2:  # 16-bit
        samples = samples.astype(np.float32) / 32768.0
    elif audio.sample_width == 4:  # 32-bit int
        samples = samples.astype(np.float32) / 2147483648.0
    return samples

def analyze_audio(pipe, audio_path: str):
    import torch
    try:
        print(audio_path)
        audio_data, sr = load_audio_mono_16k_librosa(audio_path)
        caption = pipe.run_qwen_audio(audio_data, sr)
    except Exception as e:
        print(f"\n  Error transcribing {os.path.basename(audio_path)}: {e}")
        caption = ""
    finally:
        del audio_data

    torch.cuda.empty_cache()
    return {
        "path": audio_path,
        "caption": caption,
    }
