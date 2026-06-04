import os
import json
import sys
from pathlib import Path
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError

def try_url_to_hf_repo(url: str) -> tuple[str | None, str | None]:
    """HuggingFace の URL から repo_id と filename を抽出する。"""
    if "huggingface.co" in url:
        parts = url.split("/")
        if len(parts) >= 5:
            repo_id = "/".join(parts[3:5])
            filename = "/".join(parts[5:])
            return repo_id, filename
    return None, None


def check_download_params(
    repo_id: str | None,
    output_dir: Path,
) -> tuple[bool, str, str | None]:
    """ダウンロード事前チェック。OK なら (True, "", repo_id) を返す。
    エラー時は (False, err_msg, None, None) を返す。"""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return False, "Error: huggingface_hub が見つかりません。pip install huggingface-hub でインストールしてください", None

    if not output_dir:
        return False, "Error: output_dir が指定されていません", None

    if not repo_id:
        return False, "repo_id が指定されていません", None

    return True, "", repo_id


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((HfHubHTTPError, InferenceTimeoutError)),
)
def hf_download(
    repo_id: str,
    output_dir: Path,
) -> None:
    """HuggingFace からファイルをダウンロードする。"""
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=repo_id, local_dir=str(output_dir))


def main():
    data = json.loads(sys.stdin.read())
    print("[[[initial_result_start]]]", flush=True)
    print(json.dumps({"count": 1}), flush=True)
    print("[[[initial_result_end]]]", flush=True)

    print("download task started...", flush=True)
    print("処理開始", flush=True)
    import time
    repo_id = data["repo_id"]
    output_dir = Path(data["output_dir"])
    ok, err, resolved_repo = check_download_params(repo_id, output_dir)
    if not ok:
        print(f"エラー: {err}")
        return
    try:
        print(f"{repo_id} のダウンロードを開始しました", flush=True)
        output_path = output_dir.resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        repo_name = repo_id.split("/")[-1]
        local_dir = output_path / (repo_name + ".download")
        final_dir = output_path / repo_name

        hf_download(repo_id, local_dir)
        local_dir.rename(final_dir)
        print(f"保存先: {final_dir}", flush=True)
    finally:
        print("...download task finished", flush=True)


if __name__ == "__main__":
    main()
