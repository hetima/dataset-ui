import subprocess
import traceback
from typing import Any
from nicegui import ui, background_tasks, helpers
import asyncio

xterm_option = {
    # いい感じのテーマ定義
    "theme": {
        "background": "#20222f",
        "foreground": "#c7c9d0",
        "cursor": "#f7768e",
        "selectionBackground": "#33467c",
        "black": "#15161e",
        "red": "#f7768e",
        "green": "#9ece6a",
        "yellow": "#e0af68",
        "blue": "#7aa2f7",
        "magenta": "#bb9af7",
        "cyan": "#7dcfff",
        "white": "#a9b1d6",
        "brightBlack": "#414868",
        "brightRed": "#f7768e",
        "brightGreen": "#9ece6a",
        "brightYellow": "#e0af68",
        "brightBlue": "#7aa2f7",
        "brightMagenta": "#bb9af7",
        "brightCyan": "#7dcfff",
        "brightWhite": "#c0caf5",
    },
    "cursorBlink": True,
    "fontSize": 14,
    "fontFamily": '"Cascadia Code", Menlo, monospace',
    "cols": 80,
    "rows": 24,
    "convertEol": True,
}

class XtermDialog(ui.dialog):

    def __init__(
        self,
        args: list[str],
        title: str = "",
        cd: str = "."
    ) -> None:
        super().__init__()
        self.args = args
        self.title = title
        self._is_running = False
        self._cancelled = False
        self.cd = cd
        self.show_panel()

    def _handle_value_change(self, value: Any) -> None:
        """実行中は ESC / 背景クリックによるダイアログ閉じを禁止"""
        if not value and self._is_running:
            self.open()  # 閉じようとしても即座に reopen して阻止
            return
        super()._handle_value_change(value)

    def show_panel(self):
        """xtermパネルを表示してコマンド実行開始"""
        self._process = None

        self.style("max-width: none")
        with self, ui.card().classes("").style("max-width: 70vw"):
            ui.label(self.title).classes("text-sm")
            self._terminal = ui.xterm(xterm_option).classes("dialog-xterm")
            with ui.row().classes("w-full justify-end"):
                self._stop_btn = ui.button("停止", on_click=self._stop_command)
                self._stop_btn.set_enabled(False)
                self._close_btn = ui.button("閉じる", on_click=self._safe_close)
                self._close_btn.set_enabled(False)

        background_tasks.create(
            helpers.await_with_context(self._run_command(), self.client),
            name='xterm_download',
        )

    async def _run_command(self):
        """コマンドを実行して xterm にストリーミング"""
        self._is_running = True
        self._cancelled = False
        self._stop_btn.set_enabled(True)

        try:
            self._process = subprocess.Popen(
                self.args,
                cwd=self.cd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            async def read_stream(stream) -> None:
                while True:
                    chunk = await asyncio.to_thread(stream.read, 128)
                    if not chunk:
                        break
                    self._terminal.write(chunk)

            await asyncio.gather(
                read_stream(self._process.stdout),
                read_stream(self._process.stderr),
                asyncio.to_thread(self._process.wait),
            )
            if self._cancelled:
                self._terminal.write("\r\n[キャンセルされました]\r\n")
            else:
                self._terminal.write("\r\n[完了]\r\n")
        except asyncio.CancelledError:
            self._terminal.write("\r\n[キャンセルされました(タスク)]\r\n")
        except Exception as e:
            tb = traceback.format_exc()
            self._terminal.write(f"\r\n[エラー] {type(e).__name__}: {e}")
        finally:
            self._is_running = False
            self._process = None
            self._stop_btn.set_enabled(False)
            self._close_btn.set_enabled(True)

    def _safe_close(self):
        """安全にダイアログを閉じる"""
        self.delete()

    def _stop_command(self):
        """ダウンロードプロセスを停止"""
        if self._process and self._is_running:
            self._cancelled = True
            self._process.terminate()
