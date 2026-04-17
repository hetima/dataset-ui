
import os
import gc
from pathlib import Path
from collections.abc import Generator
from music.setting import cnfg

TARGET_SAMPLE_RATE = 16000



def acestep_transcriber_models() -> list[str]:
    models_dir = cnfg.models_dir
    if not models_dir.exists():
        return []
    return [
        p.name
        for p in models_dir.iterdir()
        if p.is_dir()
        and "acestep" in p.name.lower()
        and "transcriber" in p.name.lower()
    ]

class AcestepTranscriptorPipeline:
    def __init__(self, model, processor):
        self.model = model
        self.processor = processor

    def run_qwen_audio(self, audio_data, sr, prompt_text):
        """Run a Qwen2.5-Omni model on audio with a text prompt."""
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
            result = result[result.rfind(marker) + len(marker) :]
        return result.strip()

    @classmethod
    def from_pretrained(cls, device, dtype):
        from transformers import Qwen2_5OmniForConditionalGeneration, Qwen2_5OmniProcessor
        
        local_files_only = True
        model_path = str(cnfg.models_dir / cnfg.acestep_transcriber_model)
        if not os.path.exists(model_path):
            if cnfg.acestep_transcriber_model.find("/") >= 1:
                model_path = cnfg.acestep_transcriber_model
                local_files_only = False
            else:
                raise FileNotFoundError(
                    f"モデルパス「  {str(cnfg.models_dir)}」 に「{cnfg.acestep_transcriber_model}」フォルダが存在しません"
                )
        print(f"model path: {model_path}")
        model = Qwen2_5OmniForConditionalGeneration.from_pretrained(
            model_path, torch_dtype=dtype, device_map=device, local_files_only=local_files_only
        )
        model.disable_talker()
        processor = Qwen2_5OmniProcessor.from_pretrained(
            model_path, local_files_only=local_files_only
        )

        return cls(
            model=model,
            processor=processor,
        )


def transcript_main(
    data, stop_event
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
        pipe = AcestepTranscriptorPipeline.from_pretrained(
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
        


def load_audio_mono_16k(audio_path):
    import torchaudio
    
    waveform, sr = torchaudio.load(audio_path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sr != TARGET_SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sr, TARGET_SAMPLE_RATE)
    return waveform.squeeze(0).numpy(), TARGET_SAMPLE_RATE

def load_audio_mono_16k_librosa(audio_path):
    import librosa
    waveform, _ = librosa.load(audio_path, sr=16000, mono=True)
    return waveform, 16000


def analyze_audio(pipe, audio_path):
    import torch
    try:
        print(audio_path)
        audio_data, sr = load_audio_mono_16k(audio_path)
        lyrics = pipe.run_qwen_audio(
            audio_data, sr, "*Task* Transcribe this audio in detail"
        )
    except Exception as e:
        print(f"\n  Error transcribing {os.path.basename(audio_path)}: {e}")
        lyrics = "[Instrumental]"
    finally:
        del audio_data

    torch.cuda.empty_cache()
    return {
        "path": audio_path,
        "lyrics": lyrics,
    }
