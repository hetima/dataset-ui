import os


def try_url_to_hf_repo(url):
    """Convert a HuggingFace model URL to a repo ID and filename."""
    if "huggingface.co" in url:
        parts = url.split("/")
        if len(parts) >= 5:
            repo_id = "/".join(parts[3:5])  # e.g., user/model
            filename = "/".join(parts[5:])  # e.g., model.bin
            return repo_id, filename
    return None, None

def download_hf_model(repo_id, filename, output_dir):
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
        print(f"Downloading {filename} from {repo_id} ...")
        hf_hub_download(repo_id=repo_id, filename=filename, local_dir=repo_dir)
        print(f"Saved to {save_path}")
    else:
        print(f"File already exists at {save_path}, skipping download.")
    return save_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download a HuggingFace model.")
    parser.add_argument("--repo-id", help="HuggingFace repo ID (e.g., 'user/model')")
    parser.add_argument("--filename", help="Filename to download from the repo")
    parser.add_argument(
        "--output-dir",
        help="Directory to save the downloaded file (e.g., 'diffusion_models')",
    )
    parser.add_argument("--url", help="HuggingFace model URL (alternative to repo-id and filename)")
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
        download_hf_model(repo_id, filename, args.output_dir)
    except KeyboardInterrupt:
        print("Process interrupted by user. Exiting.")
        exit(1)
