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
    filename: str | None,
    url: str | None,
) -> tuple[bool, str, str | None, str | None]:
    """ダウンロード事前チェック。OK なら (True, "", repo_id, filename) を返す。
    エラー時は (False, err_msg, None, None) を返す。"""
    if not shutil.which("hf"):
        return False, "Error: hfコマンドが見つかりません。pip install huggingface-hub でインストールしてください", None, None

    if not output_dir:
        return False, "Error: output_dir が指定されていません", None, None

    if url:
        repo_id, filename = try_url_to_hf_repo(url)
        err = "Error: url が huggingface のものではありません"
    else:
        err = "repo_id と filename が指定されていません"

    if not repo_id or not filename:
        return False, err, None, None

    return True, "", repo_id, filename


def download_model(
    output_dir: str,
    repo_id: str | None = None,
    filename: str | None = None,
    url: str | None = None,
) -> None:
    """HuggingFace からファイルをダウンロードする。
    事前チェック → XtermDialog ダイアログでコマンド実行。"""
    ok, err, resolved_repo, resolved_file = check_download_params(
        output_dir, repo_id, filename, url
    )
    if not ok:
        show_error_dialog(err)
        return

    assert resolved_repo is not None and resolved_file is not None

    script = str(Path(__file__).resolve().parent.parent / "cli" / "hf_dl_ckpt.py")
    args = [
        sys.executable, script,
        "--repo-id", resolved_repo,
        "--filename", resolved_file,
        "--output-dir", output_dir,
    ]
    XtermDialog(args, title=f"{resolved_repo} / {resolved_file}").open()
