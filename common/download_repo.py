import os
import shutil
import sys
from pathlib import Path

from common.xterm_dialog import XtermDialog
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
    output_dir: str,
    repo_id: str | None,
) -> tuple[bool, str, str | None]:
    """ダウンロード事前チェック。OK なら (True, "", repo_id) を返す。
    エラー時は (False, err_msg, None, None) を返す。"""
    if not shutil.which("hf"):
        return False, "Error: hfコマンドが見つかりません。pip install huggingface-hub でインストールしてください", None

    if not output_dir:
        return False, "Error: output_dir が指定されていません", None

    if not repo_id:
        return False, "repo_id が指定されていません", None

    return True, "", repo_id


def download_repo(
    repo_id: str,
    output_dir: str,
) -> None:
    """HuggingFace からファイルをダウンロードする。
    事前チェック → XtermDialog ダイアログでコマンド実行。"""
    ok, err, resolved_repo = check_download_params(
        output_dir, repo_id
    )
    if not ok:
        show_error_dialog(err)
        return

    assert resolved_repo is not None

    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    local_dir = str(output_path / resolved_repo.split("/")[-1])

    args = [
        "hf", "download", resolved_repo,
        "--local-dir", local_dir,
    ]
    XtermDialog(args, title=f"ダウンロード: {resolved_repo}").open()
