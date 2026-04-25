from pathlib import Path
import shutil
from typing import Any
from nicegui import ui
import asyncio
import os

class HfDownload(ui.dialog):

    def __init__(
        self,
        output_dir: str,
        repo_id: str|None,
        filename: str|None,
        url: str|None,
    ) -> None:
        super().__init__()
        self.output_dir = output_dir
        self.repo_id = repo_id
        self.filename = filename
        self.url = url
        self._is_running = False
        self._cancelled = False
        can_run, err = self.check_param()
        if can_run:
            self.show_panel()
        else:
            self.show_err_panel(err)

    def _handle_value_change(self, value: Any) -> None:
        """実行中は ESC / 背景クリックによるダイアログ閉じを禁止"""
        if not value and self._is_running:
            self.open()  # 閉じようとしても即座に reopen して阻止
            return
        super()._handle_value_change(value)

    def check_param(self) -> tuple[bool, str]:
        def try_url_to_hf_repo(url):
            """Convert a HuggingFace model URL to a repo ID and filename."""
            if "huggingface.co" in url:
                parts = url.split("/")
                if len(parts) >= 5:
                    repo_id = "/".join(parts[3:5])  # e.g., user/model
                    filename = "/".join(parts[5:])  # e.g., model.bin
                    return repo_id, filename
            return None, None

        if not shutil.which("hf"):
            return (
                False,
                "Error: hfコマンドが見つかりません。pip install huggingface-hub でインストールしてください",
            )
        if not self.output_dir:
            return False, "Error: output_dir が指定されていません"
        if self.url:
            self.repo_id, self.filename = try_url_to_hf_repo(self.url)
            err = "Error: url が huggingface のものではありません"
        else:
            err = "repo_id と filename が指定されていません"

        if not self.repo_id or not self.filename:
            return False, err
        return True, ""

    def show_panel(self):
        """xtermパネルを表示してダウンロード開始"""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        self._process: asyncio.subprocess.Process | None = None

        with self, ui.card().classes("w-120"):
            ui.label(f"{self.repo_id} / {self.filename}").classes("text-sm")
            self._terminal = ui.xterm({"cols": 100, "rows": 15, "convertEol": True})
            with ui.row().classes("w-full justify-end"):
                self._stop_btn = ui.button("停止", on_click=self._stop_download)
                self._stop_btn.set_enabled(False)
                ui.button("閉じる", on_click=self.delete)

        asyncio.create_task(self._run_download())

    async def _run_download(self):
        """hf download コマンドを実行して xterm にストリーミング"""
        if not self.repo_id or not self.filename:
            return
        repo_dir = os.path.join(self.output_dir, self.repo_id.replace("/", "--"))
        os.makedirs(repo_dir, exist_ok=True)
        save_path = os.path.join(repo_dir, self.filename)
        args = ["hf", "download", self.repo_id, self.filename, "--local-dir", save_path]
        self._is_running = True
        self._cancelled = False
        self._stop_btn.set_enabled(True)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def write_to_terminal(stream: asyncio.StreamReader) -> None:
                while chunk := await stream.read(128):
                    self._terminal.write(chunk)

            await asyncio.gather(
                write_to_terminal(self._process.stdout) if self._process.stdout else asyncio.sleep(0),
                write_to_terminal(self._process.stderr) if self._process.stderr else asyncio.sleep(0),
                self._process.wait(),
            )
            if self._cancelled:
                self._terminal.write("\r\n[キャンセルされました]\r\n")
            else:
                self._terminal.write("\r\n[完了]\r\n")
        except Exception as e:
            self._terminal.write(f"\r\n[エラー] {e}\r\n")
        finally:
            self._is_running = False
            self._process = None
            self._stop_btn.set_enabled(False)

    def _stop_download(self):
        """ダウンロードプロセスを停止"""
        if self._process and self._is_running:
            self._cancelled = True
            self._process.terminate()

    def show_err_panel(self, txt: str):
        """エラーを表示するパネルを表示"""
        with self, ui.card().classes("w-120"):
            ui.label(txt)
            with ui.row().classes("w-full justify-end"):
                ui.button("OK", on_click=self.delete)
