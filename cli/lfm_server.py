"""
LFM2.5-Audio ASR を OpenAI 互換 API として提供するサーバ。

起動:
    python cli/lfm_server.py --model <model_path> [--host 0.0.0.0] [--port 8000]

エンドポイント:
    POST /v1/chat/completions
        messages 内の input_audio（16kHz mono WAV の base64）を受け取り、
        cli_task_lfm_asr.py と同じ処理（無音分割 → LFM2.5-Audio ASR）で
        文字起こしし、結果を OpenAI 互換のレスポンスで返す。
    GET /v1/models
        モデル名 "auto" のみを返す。

リクエスト例:
    {
        "model": "auto",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "input_audio",
                     "input_audio": {"data": "<base64>", "format": "wav"}},
                    {"type": "text", "text": ""}
                ]
            }
        ],
        "temperature": 0
    }
"""
import argparse
import base64
import sys
import time
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from voice.cli_task_lfm_asr import LFMASRPipeline, analyze_audio_data

app = FastAPI()

# サーバ起動時にロードして常駐させるパイプライン
_pipe: LFMASRPipeline | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "auto"
    messages: list[dict]
    temperature: float = 0.0


def _extract_audio_base64(messages: list[dict]) -> str:
    """messages から最初の input_audio の base64 データを取り出す。"""
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "input_audio":
                data = part.get("input_audio", {}).get("data")
                if data:
                    return data
    raise HTTPException(status_code=400, detail="input_audio が見つかりません")


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {"id": "auto", "object": "model", "created": int(time.time()), "owned_by": "lfm"}
        ],
    }


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    if _pipe is None:
        raise HTTPException(status_code=503, detail="モデルが読み込まれていません")

    audio_b64 = _extract_audio_base64(req.messages)
    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="input_audio の base64 デコードに失敗しました")

    transcript = analyze_audio_data(_pipe, audio_bytes)

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "auto",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": transcript},
                "finish_reason": "stop",
            }
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="LFM2.5-Audio ASR OpenAI 互換 API サーバ")
    parser.add_argument("--model-dir", required=True, help="LFM2.5-Audio モデルパス")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7868, help="デフォルト:7868")
    args = parser.parse_args()

    global _pipe
    print("モデルを読み込んでいます...", flush=True)
    _pipe = LFMASRPipeline.from_pretrained(args.model_dir)
    print(f"サーバを起動します: http://{args.host}:{args.port}", flush=True)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
