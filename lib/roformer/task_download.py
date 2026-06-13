"""CpuTaskDialog 用ダウンロードワーカー。"""
import json
import multiprocessing
import multiprocessing.queues
import os
from pathlib import Path
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)
def _log(queue: multiprocessing.queues.Queue, text: str):  # type: ignore[type-arg]
    queue.put({"type": "log", "text": text})

try:
    from huggingface_hub import hf_hub_download, download_bucket_files
except ImportError:
    print("[エラー] huggingface_hub が見つかりません。pip install huggingface_hub")


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10))
def do_download(repo_id, filename, local_dir):
    # もしrepo_idがbuckets/で始まっていたらbuckets/を取り除きdownload_bucket_filesを実行
    # そうでないならhf_hub_downloadを実行
    if repo_id.startswith("buckets/"):
        bucket_name = repo_id[len("buckets/"):]
        local_file_path = str(Path(local_dir) / filename)
        download_bucket_files(bucket_name, files=[(filename, local_file_path)])
    else:
        hf_hub_download(repo_id=repo_id, filename=filename, local_dir=local_dir)

def download_roformer_model(data: dict, queue: multiprocessing.queues.Queue, stop_event) -> dict | None:  # type: ignore[type-arg]
    """
    data keys: repo_id, filename, yamlname, output_dir, convert, metadata
    親プロセスのターミナルに tqdm が直接出力される。
    """
    _log(queue, "ダウンロード進捗は本物のターミナルの方に表示されます")

    repo_id: str = data["repo_id"]
    filename: str = data["filename"]
    yamlname: str = data.get("yamlname", "")
    output_dir: str = data["output_dir"]
    convert: bool = data.get("convert", False)
    metadata: dict = data.get("metadata", {})

    if filename.startswith("resolve/main/"):
        filename = filename[len("resolve/main/"):]
    if filename.startswith("blob/main/"):
        filename = filename[len("blob/main/"):]

    repo_dir = os.path.join(output_dir, repo_id.replace("/", "--"))
    os.makedirs(repo_dir, exist_ok=True)
    save_path = os.path.join(repo_dir, filename)

    if stop_event.is_set():
        return None

    safetensors_path = Path(save_path).with_suffix(".safetensors")
    if safetensors_path.exists():
        _log(queue, f"既に存在します: {safetensors_path}")
    else:
        _log(queue, f"ダウンロード: {filename} from {repo_id}")
        do_download(repo_id=repo_id, filename=filename, local_dir=repo_dir)
        _log(queue, f"{Path(filename).name} ダウンロード完了")

        if stop_event.is_set():
            return None

        if yamlname:
            _log(queue, f"ダウンロード: {yamlname}")
            do_download(repo_id=repo_id, filename=yamlname, local_dir=repo_dir)
            _log(queue, f"{Path(yamlname).name} ダウンロード完了")
            yaml_src = Path(repo_dir) / yamlname
            yaml_dst = Path(save_path).with_suffix(".yaml")
            if yaml_src.exists() and yaml_src != yaml_dst:
                yaml_src.rename(yaml_dst)
                _log(queue, f"yaml → {yaml_dst.name}")

    if stop_event.is_set():
        return None

    _log(queue, f"保存先: {save_path}")

    # post processing
    model_path = Path(save_path)
    if model_path.suffix in (".ckpt", ".pth", ".pt", ".bin") and model_path.exists():
        try:
            from picklescan import scanner
            _log(queue, "picklescan 実行中...")
            scan_result = scanner.scan_file_path(str(model_path))
            if scan_result.scan_err or scan_result.issues_count != 0:
                _log(queue, "警告: picklescan で問題が検出されました")
            else:
                _log(queue, "picklescan: 問題なし")
        except ImportError:
            _log(queue, "picklescan はスキップされました（未インストール）")

        if convert and not safetensors_path.exists():
            _log(queue, "safetensors に変換中...")
            import torch
            from safetensors.torch import save_file
            checkpoint = torch.load(str(model_path), map_location="cpu")
            weights = checkpoint.get("state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
            weights = {k: v.clone() for k, v in weights.items()}
            save_file(weights, str(safetensors_path))
            _log(queue, "変換完了")

    # メタデータ保存
    if metadata:
        meta_path = Path(save_path).parent / (Path(save_path).stem + ".meta.json")
        meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        _log(queue, f"メタデータ保存: {meta_path.name}")

    return {"repo_id": repo_id, "filename": filename, "save_path": save_path}
