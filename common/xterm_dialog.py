from typing import Any
from nicegui import ui
import asyncio

class XtermDialog(ui.dialog):

    def __init__(
        self,
        args: list[str],
        title: str = "",
    ) -> None:
        super().__init__()
        self.args = args
        self.title = title
        self._is_running = False
        self._cancelled = False
        self.show_panel()

    def _handle_value_change(self, value: Any) -> None:
        """実行中は ESC / 背景クリックによるダイアログ閉じを禁止"""
        if not value and self._is_running:
            self.open()  # 閉じようとしても即座に reopen して阻止
            return
        super()._handle_value_change(value)

    def show_panel(self):
        """xtermパネルを表示してコマンド実行開始"""
        self._process: asyncio.subprocess.Process | None = None

        with self, ui.card().classes("w-120"):
            ui.label(self.title).classes("text-sm")
            self._terminal = ui.xterm({"cols": 100, "rows": 15, "convertEol": True})
            with ui.row().classes("w-full justify-end"):
                self._stop_btn = ui.button("停止", on_click=self._stop_download)
                self._stop_btn.set_enabled(False)
                ui.button("閉じる", on_click=self.delete)

        asyncio.create_task(self._run_download())

    async def _run_download(self):
        """コマンドを実行して xterm にストリーミング"""
        self._is_running = True
        self._cancelled = False
        self._stop_btn.set_enabled(True)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.args,
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
