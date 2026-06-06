"""
LFM2.5-Audio ASR CLI タスク。
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
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from voice.cli_task_segment_silence import split_one_file


class LFMASRPipeline:
    def __init__(self, model, processor):
        self.model = model
        self.processor = processor

    def transcribe(self, audio_data, sr):
        """LFM2.5-Audio モデルで音声を文字起こしする"""
        import torch
        from liquid_audio import ChatState

        chat = ChatState(self.processor)

        chat.new_turn("system")
        chat.add_text("Perform ASR in japanese.")
        chat.end_turn()

        chat.new_turn("user")
        wav = torch.from_numpy(audio_data).unsqueeze(0)
        chat.add_audio(wav, sr)
        chat.end_turn()

        chat.new_turn("assistant")

        token_ids = []
        for t in self.model.generate_sequential(**chat, max_new_tokens=512):
            if t.numel() == 1:
                token_ids.append(int(t.item()))
        return self.processor.text.decode(token_ids, skip_special_tokens=True).strip()

    @classmethod
    def from_pretrained(cls, model_path: str|Path):
        from liquid_audio import LFM2AudioModel, LFM2AudioProcessor

        if type(model_path) == str and not os.path.exists(model_path):
            if "/" in model_path:
                pass  # HuggingFace Hub からダウンロード
            else:
                raise FileNotFoundError(f"「{model_path}」が存在しません")
        else:
            model_path = Path(model_path)
        print(f"model path: {model_path}", flush=True)
        processor = LFM2AudioProcessor.from_pretrained(model_path).eval()
        model = LFM2AudioModel.from_pretrained(model_path).eval()
        return cls(model=model, processor=processor)


def load_audio_mono_16k_librosa(audio_path: str):
    import librosa
    waveform, _ = librosa.load(audio_path, sr=16000, mono=True)
    return waveform, 16000


def analyze_audio(pipe, audio_path: str) -> dict:
    import numpy as np
    
    chunks = split_one_file(audio_path, min_silence_len=300, silence_thresh=-40, min_sec=15, max_sec=20, fade_ms=10, gap_ms=100)
    if len(chunks) > 1:
        print(f"divided into {len(chunks)} chunks", flush=True)
    
    transcripts = []
    for i, chunk in enumerate(chunks):
        try:
            samples = np.array(chunk.get_array_of_samples()).astype(np.float32)
            if chunk.sample_width == 2:
                samples /= 32768.0
            elif chunk.sample_width == 4:
                samples /= 2147483648.0
            # ステレオの場合はモノラルに変換
            channels = chunk.channels or 1
            if channels > 1:
                samples = samples.reshape(-1, channels).mean(axis=1)
            sr = chunk.frame_rate
            transcript = pipe.transcribe(samples, sr)
        except Exception as e:
            print(f"\n  Error transcribing chunk {i+1} of {os.path.basename(audio_path)}: {e}", flush=True)
            transcript = ""
        transcripts.append(transcript.strip().strip("<|im_end|>"))

    return {
        "path": audio_path,
        "transcript": " ".join(t for t in transcripts if t),
    }


def main():
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
        pipe = LFMASRPipeline.from_pretrained(model_path)
    except FileNotFoundError as e:
        print(f"エラー: {e}", flush=True)
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


if __name__ == "__main__":
    main()
