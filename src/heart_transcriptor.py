from transformers.pipelines.automatic_speech_recognition import (
    AutomaticSpeechRecognitionPipeline,
)
from transformers.models.whisper.modeling_whisper import WhisperForConditionalGeneration
from transformers.models.whisper.processing_whisper import WhisperProcessor
import torch
import os
import gc
from pathlib import Path
from collections.abc import Generator
from src.setting import cnfg

class HeartTranscriptorPipeline(AutomaticSpeechRecognitionPipeline):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def from_pretrained(
        cls, models_path: Path, device: torch.device, dtype: torch.dtype
    ):
        hearttranscriptor_path = str(models_path / "HeartTranscriptor-oss")
        if os.path.exists(hearttranscriptor_path):
            model = WhisperForConditionalGeneration.from_pretrained(
                hearttranscriptor_path, torch_dtype=dtype, low_cpu_mem_usage=True
            )
            processor = WhisperProcessor.from_pretrained(hearttranscriptor_path)
        else:
            raise FileNotFoundError(
                f"モデルパス「  {str(models_path)}」 に「HeartTranscriptor-oss」フォルダが存在しません。ダウンロードしてください"
            )

        return cls(
            model=model,
            tokenizer=processor.tokenizer, # type: ignore
            feature_extractor=processor.feature_extractor, # type: ignore
            device=device,
            dtype=dtype,
            chunk_length_s=30,
            batch_size=16,
            processor=processor,
        )

def transcript_main(data, stop_event) -> Generator[tuple[float, str], None, dict]:
    cnfg.load()
    new_data = []
    yield 0, "処理開始"
    cnt = len(data)
    if cnt == 0:
        yield 1, "完了"
        return {"err": "処理するファイルがありませんでした"}
    try:
        pipe = HeartTranscriptorPipeline.from_pretrained(
            cnfg.morels_dir,
            device=torch.device("cuda"),
            dtype=torch.float16,
        )
    except FileNotFoundError as e:
        yield 1, "エラー"
        return {"err": e}
    if pipe.model is None:
        yield 1, "エラー"
        return {"err": "モデルを読み込めませんでした"}
    i = 0
    try:
        for path in data:
            if stop_event.is_set():
                yield 1, "キャンセル"
                return {"result": []}
            result = analyze_audio(pipe, path)
            i = i + 1
            new_data.append(result)
            yield i / cnt, f"処理 ({i}/{cnt})"
        return {"result": new_data}
    finally:
        del pipe
        gc.collect()
        torch.cuda.empty_cache()

def analyze_audio(pipe, audio_path):
    """

    """

    with torch.no_grad():
        result = pipe(
            audio_path,
            **{
                "max_new_tokens": 256,
                "num_beams": 2,
                "task": "transcribe",
                "condition_on_prev_tokens": False,
                "compression_ratio_threshold": 1.8,
                "temperature": (0.0, 0.1, 0.2, 0.4),
                "logprob_threshold": -1.0,
                "no_speech_threshold": 0.4,
            },
        )
    text = result if isinstance(result, str) else result.get("text", str(result))
    torch.cuda.empty_cache()
    return {
        "path": audio_path,
        "lyrics": text,
    }
