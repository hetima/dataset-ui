import json
import os
import sys
import time
from pathlib import Path
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

# os.environ["PYTHONUNBUFFERED"] = "1"
# sys.stderr.isatty = lambda: True
# sys.stdout.isatty = lambda: True
# os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "0"

try:
    from huggingface_hub import hf_hub_download
except ImportError:
    raise ImportError(
        "huggingface_hub is required for download. "
        "Install with:  pip install huggingface_hub"
    )


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10))
def do_download(repo_id, filename, local_dir):
    hf_hub_download(
        repo_id=repo_id, filename=filename, local_dir=local_dir
    )


def download_hf_model(repo_id: str, filename: str, yamlname: str, output_dir: str):
    """Download a model from HuggingFace into ComfyUI's diffusion_models folder."""

    if filename.startswith("resolve/main/"):
        filename = filename[len("resolve/main/"):]
    if filename.startswith("blob/main/"):
        filename = filename[len("blob/main/"):]

    repo_dir = os.path.join(output_dir, repo_id.replace("/", "--"))
    os.makedirs(repo_dir, exist_ok=True)
    save_path = os.path.join(repo_dir, filename)

    safetensors_path = Path(save_path).with_suffix(".safetensors")
    if safetensors_path.exists():
        print(
            f"safetensors file already exists at {str(safetensors_path)}, skipping download.",
            flush=True,
        )
    else:
        print(f"Downloading {filename} from {repo_id} ...", flush=True)
        do_download(
            repo_id=repo_id, filename=filename, local_dir=repo_dir
        )
        print(f"{Path(filename).name} ダウンロード完了", flush=True)
        if yamlname:
            print(f"Downloading {yamlname} ...", flush=True)
            do_download(
                repo_id=repo_id, filename=yamlname, local_dir=repo_dir
            )
            print(f"{Path(yamlname).name} ダウンロード完了", flush=True)
            # yaml をモデルファイルと同名にリネーム
            yaml_src = Path(repo_dir) / yamlname
            yaml_dst = Path(save_path).with_suffix(".yaml")
            if yaml_src.exists() and yaml_src != yaml_dst:
                yaml_src.rename(yaml_dst)
                print(f"Renamed yaml to {yaml_dst.name}", flush=True)

    # tqdmの出力が別スレッドで書き込まれるため、フラッシュして出力を同期する
    sys.stdout.flush()
    sys.stderr.flush()
    print("", flush=True)
    print(f"Saved to {save_path}")

    return save_path


def post_processing(path: Path, convert: bool = False):
    if not path.exists():
        return
    try:
        from picklescan import scanner
        print("picklescan start.", flush=True)
        scan_result = scanner.scan_file_path(str(path))
        if scan_result.scan_err:
            print(f"Error: picklescan failed. file: {str(path)}", flush=True)
            return
        if scan_result.issues_count != 0:
            print(f"Warning: picklescan reported issue. file: {str(path)}", flush=True)
            return
        print("picklescan finished with no issues.", flush=True)
    except ImportError:
        print("picklescan is not installed and skipped.", flush=True)

    safetensors_path = path.with_suffix(".safetensors")
    if safetensors_path.exists():
        return
    if convert:
        print("Starting convert to safetensors...", flush=True)
        import torch
        from safetensors.torch import save_file

        checkpoint = torch.load(str(path), map_location="cpu")
        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            weights = checkpoint["state_dict"]
        else:
            weights = checkpoint
        weights = {k: v.clone() for k, v in weights.items()}
        save_file(weights, str(safetensors_path))
        print("convert to safetensors finished.", flush=True)


def start_operation(
    repo_id: str, filename: str, yamlname: str, output_dir: str, convert: bool = False
):
    save_path = Path(download_hf_model(repo_id, filename, yamlname, output_dir))
    if save_path.suffix == ".safetensors":
        return
    if save_path.suffix in [".ckpt", ".pth", ".pt", "bin"]:
        post_processing(save_path, convert)


def save_metadata(save_path: str, metadata: dict):
    """モデルと同じ場所に <モデル名（拡張子抜き）>.meta.json を保存する。"""
    p = Path(save_path)
    meta_path = p.parent / (p.stem + ".meta.json")
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Metadata saved to {meta_path}", flush=True)


def main():
    # stderr を stdout にマージして xterm に表示されるようにする

    # sys.stderr = sys.stdout
        
    data = json.loads(sys.stdin.read())
    repo_id: str = data["repo_id"]
    filename: str = data["filename"]
    yamlname: str = data.get("yamlname", "")
    output_dir: str = data["output_dir"]
    convert: bool = data.get("convert", False)
    metadata: dict = data.get("metadata", {})

    print("[[[initial_result_start]]]", flush=True)
    print(json.dumps({"count": 1}), flush=True)
    print("[[[initial_result_end]]]", flush=True)
    print("ダウンロードを開始します", flush=True)
    try:
        start_operation(repo_id, filename, yamlname, output_dir, convert)
    except KeyboardInterrupt:
        print("中断されました。", flush=True)
        sys.exit(1)

    if metadata:
        repo_dir = os.path.join(output_dir, repo_id.replace("/", "--"))
        save_path = os.path.join(repo_dir, filename)
        save_metadata(save_path, metadata)

    print("[[[part_result_start]]]", flush=True)
    print(json.dumps({"type": "result", "repo_id": repo_id, "filename": filename}), flush=True)
    print("[[[part_result_end]]]", flush=True)


if __name__ == "__main__":
    main()
