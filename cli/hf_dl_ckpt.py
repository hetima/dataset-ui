import os
from pathlib import Path

def try_url_to_hf_repo(url: str):
    """Convert a HuggingFace model URL to a repo ID and filename."""
    if "huggingface.co" in url:
        parts = url.split("/")
        if len(parts) >= 5:
            repo_id = "/".join(parts[3:5])  # e.g., user/model
            filename = "/".join(parts[5:])  # e.g., model.bin
            return repo_id, filename
    return None, None

def download_hf_model(repo_id: str, filename: str, output_dir: str):
    """Download a model from HuggingFace into ComfyUI's diffusion_models folder."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise ImportError(
            "huggingface_hub is required for auto-download. "
            "Install with:  pip install huggingface_hub"
        )
    if filename.startswith("resolve/main/"):
        filename = filename[len("resolve/main/") :]
    if filename.startswith("blob/main/"):
        filename = filename[len("blob/main/") :]

    repo_dir = os.path.join(output_dir, repo_id.replace("/", "--"))
    os.makedirs(repo_dir, exist_ok=True)
    save_path = os.path.join(repo_dir, filename)
    if not os.path.exists(save_path):
        safetensors_path = Path(save_path).with_suffix(".safetensors")
        if safetensors_path.exists():
            print(f"safetensors file already exists at {str(safetensors_path)}, skipping download.")
        print(f"Downloading {filename} from {repo_id} ...")
        hf_hub_download(repo_id=repo_id, filename=filename, local_dir=repo_dir)
        print(f"Saved to {save_path}")
    else:
        print(f"File already exists at {save_path}, skipping download.")
    return save_path

def post_processing(path: Path, convert: bool = False):
    if not path.exists():
        return
    try:
        from picklescan import scanner
    except ImportError:
        raise ImportError(
            "picklescan is required."
            "Install with:  pip install picklescan"
        )
    print("picklescan start.")
    scan_result = scanner.scan_file_path(str(path))
    if scan_result.scan_err:
        print(f"Error: picklescan failed. file: {str(path)}")
        return
    if scan_result.issues_count != 0:
        print(f"Warning: picklescan reported issue. file: {str(path)}")
        return
    print("picklescan finished with no issues.")
    safetensors_path = path.with_suffix(".safetensors")
    if safetensors_path.exists():
        return
    if convert:
        print("Starting convert to safetensors...")
        import torch
        from safetensors.torch import save_file

        checkpoint = torch.load(str(path), map_location="cpu")
        if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            weights = checkpoint["state_dict"]
        else:
            weights = checkpoint
        weights = {k: v.clone() for k, v in weights.items()}
        save_file(weights, str(safetensors_path))
        print("convert to safetensors finished.")


def start_operation(repo_id: str, filename: str, output_dir: str, convert: bool = False):
    save_path = Path(download_hf_model(repo_id, filename, output_dir))
    if save_path.suffix == ".safetensors":
        return
    if save_path.suffix in [".ckpt", ".pth", ".pt", "bin"]:
        post_processing(save_path, convert)

    # if tpath.exists():

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download a ckpt model from HuggingFace and scan with picklescan."
    )
    parser.add_argument("--repo-id", help="HuggingFace repo ID (e.g., 'user/model')")
    parser.add_argument("--filename", help="Filename to download from the repo")
    parser.add_argument(
        "--output-dir",
        help="Directory to save the downloaded file (e.g., 'diffusion_models')",
    )
    parser.add_argument("--url", help="HuggingFace model URL (alternative to repo-id and filename)")
    parser.add_argument("--convert", action="store_true", help="Convert to safetensors after download(beta)")
    args = parser.parse_args()

    if args.url:
        if not args.output_dir:
            print("Error: --output-dir is required.")
            exit(1)
        repo_id, filename = try_url_to_hf_repo(args.url)
        if not repo_id or not filename:
            print("Error: Invalid URL format.")
            exit(1)
    else:
        if not args.repo_id or not args.filename or not args.output_dir:
            print(
                "Error: All arguments (--repo-id, --filename, --output-dir) are required."
            )
            exit(1)
        repo_id = args.repo_id
        filename = args.filename

    try:
        start_operation(repo_id, filename, args.output_dir, args.convert)
    except KeyboardInterrupt:
        print("Process interrupted by user. Exiting.")
        exit(1)
