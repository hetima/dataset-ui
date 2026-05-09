import os
import shutil
import sys
from pathlib import Path
from collections.abc import Generator
from tenacity import retry, stop_after_attempt, wait_exponential

from common.message_dialog import show_error_dialog


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


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=4, max=10))
def hf_download(
    repo_id: str,
    output_dir: Path,
) -> None:
    """HuggingFace からファイルをダウンロードする。"""
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=repo_id, local_dir=str(output_dir))


def download_repo_main(
    data: dict, stop_event
) -> Generator[tuple[float, str, dict | None], None, dict]:
    print("download task started...")
    yield 0, "処理開始", None
    repo_id = data["repo_id"]
    output_dir = data["output_dir"]
    ok, err, resolved_repo = check_download_params(repo_id, output_dir)
    if not ok:
        yield 1, "エラー", None
        return {"err": err}
    try:
        yield 0, f"{repo_id} のダウンロードを開始しました。進捗はターミナルを参照してください", None
        output_path = output_dir.resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        local_dir = output_path / repo_id.split("/")[-1]

        hf_download(repo_id, local_dir)
        return {"result": []}
    finally:
        print("...download task finished")
