import sys
from pathlib import Path
import argparse
import os
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
for p in (str(PROJECT_ROOT), str(LIB_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

KNOWN_MODEL_NAMES = {"Irodori-TTS-500M-v3", "Irodori-TTS-600M-v3-VoiceDesign"}

parser = argparse.ArgumentParser(description="Irodori TTS サーバ")
parser.add_argument("--model-path", default=None, help="モデルパス（省略時はconfig.jsonから自動解決）")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=7867, help="デフォルト:7867")
args = parser.parse_args()

model_name = "Irodori-TTS-500M-v3"
voices_dir = "voices"
if args.model_path in KNOWN_MODEL_NAMES:
    model_name = args.model_path
    args.model_path = None


config_path = PROJECT_ROOT / "config.json"
try:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    models_dir = config.get("models_dir")
    if not models_dir:
        raise ValueError
    if args.model_path is None:
        args.model_path = str(Path(models_dir) / "irodori-tts" / model_name / "model.safetensors")
    voices_dir = str(Path(models_dir) / "irodori-tts_voices")
    hf_token = config.get("hf_token")
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
except Exception:
    print("エラー: config.jsonの読み込みに失敗しました", file=sys.stderr)
    sys.exit(1)

if not Path(args.model_path).exists():
    print(f"エラー: モデルファイルが見つかりません: {args.model_path}", file=sys.stderr)
    sys.exit(1)

print(f"model:{args.model_path}")
os.environ["IRODORI_CHECKPOINT"] = args.model_path
os.environ["IRODORI_VOICES_DIR"] = voices_dir
# os.environ["IRODORI_PRELOAD"] = "1"

sys.argv = [__file__, "--host", args.host, "--port", str(args.port)]

from irodori_tts_server.__main__ import main # type: ignore

if __name__ == "__main__":
    main()
