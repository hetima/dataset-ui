import json
import os
import subprocess
from typing import Any, Callable
from nicegui import ui, background_tasks, helpers
import asyncio
from common.setting import cnfg

INITIAL_RESULT_START = "[[[initial_result_start]]]"
INITIAL_RESULT_END = "[[[initial_result_end]]]"
PART_RESULT_START = "[[[part_result_start]]]"
PART_RESULT_END = "[[[part_result_end]]]"

xterm_option = {
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
    "rows": 26,
    "convertEol": True,
}


class XtermDialog(ui.dialog):

    def __init__(
        self,
        args: list[str],
        title: str = "",
        cd: str = ".",
        input_json: Any = None,
        env: dict[str, str] | None = None,
        initial_callback: Callable[[int], None] | None = None,
        part_callback: Callable[[dict], None] | None = None,
        finish_callback: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__()
        self.props("persistent")
        self.args = args
        self.title = title
        self._is_running = False
        self._cancelled = False
        self.cd = cd
        self._input_json = input_json
        self._env = env
        self._initial_callback = initial_callback
        self._part_callback = part_callback
        self._finish_callback = finish_callback
        self._total_count: int = 0
        self._part_count: int = 0
        self._success: bool = False
        self._show_panel()

    def _handle_value_change(self, value: Any) -> None:
        """実行中は ESC / 背景クリックによるダイアログ閉じを禁止"""
        if not value and self._is_running:
            self.open()
            return
        super()._handle_value_change(value)

    def _show_panel(self):
        self._process: subprocess.Popen | None = None
        self._is_running = True

        self.style("max-width: none")
        with self, ui.card().style("width: fit-content; max-width: 95vw"):
            ui.label(self.title).classes("text-sm")
            self._terminal = ui.xterm(xterm_option).classes("dialog-xterm")
            with ui.row().classes("w-full justify-end items-center"):
                self._progress = ui.circular_progress(min=0, max=1, value=0, size="30px").props("instant-feedback")
                self._progress.set_visibility(False)
                self._stop_btn = ui.button("停止", on_click=self._stop_command)
                self._stop_btn.set_enabled(False)
                self._close_btn = ui.button("閉じる", on_click=self._safe_close)
                self._close_btn.set_enabled(False)

        background_tasks.create(
            helpers.await_with_context(self._run_command(), self.client),  # type: ignore[arg-type]
            name='xterm_run',
        )

    async def _run_command(self):
        """コマンドを実行して xterm にストリーミング"""
        self._is_running = True
        self._cancelled = False
        self._stop_btn.set_enabled(True)
        success = False

        try:
            stdin_data = json.dumps(self._input_json).encode() if self._input_json is not None else None
            extra_env: dict[str, str] = {}
            if cnfg.hf_token:
                extra_env["HF_TOKEN"] = cnfg.hf_token
            if self._env:
                extra_env.update(self._env)
            env = {**os.environ, **extra_env} if extra_env else None
            self._process = subprocess.Popen(
                self.args,
                cwd=self.cd,
                stdin=subprocess.PIPE if stdin_data is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            if stdin_data is not None:
                await asyncio.to_thread(self._process.stdin.write, stdin_data)  # type: ignore[union-attr]
                self._process.stdin.close()  # type: ignore[union-attr]

            async def read_stdout() -> None:
                """stdout を行単位で読み、マーカー間の JSON をコールバックに渡す"""
                json_buf: list[str] = []
                block_type: str = ""  # "initial" | "part" | ""
                while True:
                    line_bytes = await asyncio.to_thread(self._process.stdout.readline)  # type: ignore[union-attr]
                    if not line_bytes:
                        break
                    line = line_bytes.decode(errors='replace').rstrip('\r\n')
                    if line == INITIAL_RESULT_START:
                        block_type = "initial"
                        json_buf = []
                        continue
                    if line == PART_RESULT_START:
                        block_type = "part"
                        json_buf = []
                        continue
                    if line in (INITIAL_RESULT_END, PART_RESULT_END):
                        try:
                            data = json.loads('\n'.join(json_buf))
                            if block_type == "initial":
                                self._total_count = data.get("count", 0)
                                if self._total_count > 0:
                                    self._progress.props(f"max={self._total_count}")
                                    self._progress.value = 0
                                    self._progress.set_visibility(True)
                                if self._initial_callback:
                                    self._initial_callback(self._total_count)
                            elif block_type == "part":
                                self._part_count += 1
                                self._progress.value = self._part_count
                                if self._part_callback:
                                    self._part_callback(data)
                        except Exception:
                            pass
                        json_buf = []
                        block_type = ""
                        continue
                    if block_type:
                        json_buf.append(line)
                    else:
                        self._terminal.write((line + '\r\n').encode())

            async def read_stderr() -> None:
                while True:
                    chunk = await asyncio.to_thread(self._process.stderr.read, 128)  # type: ignore[union-attr]
                    if not chunk:
                        break
                    self._terminal.write(chunk)

            await asyncio.gather(
                read_stdout(),
                read_stderr(),
                asyncio.to_thread(self._process.wait),
            )

            if self._cancelled:
                self._terminal.write("\r\n[キャンセルされました]\r\n".encode())
            else:
                self._terminal.write("\r\n[完了]\r\n".encode())
                success = True

        except asyncio.CancelledError:
            self._terminal.write("\r\n[キャンセルされました(タスク)]\r\n".encode())
        except Exception as e:
            self._terminal.write(f"\r\n[エラー] {type(e).__name__}: {e}".encode())
        finally:
            self._is_running = False
            self._process = None
            self._success = success
            self._progress.set_visibility(False)
            self._stop_btn.set_enabled(False)
            self._close_btn.set_enabled(True)

    def _safe_close(self):
        if self._finish_callback:
            self._finish_callback(self._success)
        try:
            self.delete()
        except ValueError:
            pass

    def _stop_command(self):
        if self._process and self._is_running:
            self._cancelled = True
            self._process.terminate()
