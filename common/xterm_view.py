import asyncio
import json
import subprocess
from typing import Any, Callable

from nicegui import background_tasks, helpers, ui

from common.xterm_dialog import (
    INITIAL_RESULT_END,
    INITIAL_RESULT_START,
    PART_RESULT_END,
    PART_RESULT_START,
    xterm_option,
)


class XtermView(ui.column):
    """CLI タスクの出力を配置用 xterm にストリーミング表示する。"""

    def __init__(self, title: str = "") -> None:
        super().__init__()
        self._process: subprocess.Popen | None = None
        self._is_running = False
        self._cancelled = False
        self._success = False
        self._total_count = 0
        self._part_count = 0
        self._initial_callback: Callable[[int], None] | None = None
        self._part_callback: Callable[[dict], None] | None = None
        self._finish_callback: Callable[[bool], None] | None = None

        self.classes("gap-1")
        with self:
            if title:
                ui.label(title).classes("text-sm")
            self._terminal = ui.xterm(xterm_option).classes("dialog-xterm")
            with ui.row().classes("w-full justify-end items-center"):
                self._progress = (
                    ui.circular_progress(min=0, max=1, value=0, size="30px")
                    .props("instant-feedback")
                )
                self._progress.set_visibility(False)

    @property
    def is_running(self) -> bool:
        """タスク実行中なら True を返す。"""
        return self._is_running

    def run(
        self,
        args: list[str],
        cd: str = ".",
        input_json: Any = None,
        initial_callback: Callable[[int], None] | None = None,
        part_callback: Callable[[dict], None] | None = None,
        finish_callback: Callable[[bool], None] | None = None,
    ) -> bool:
        """CLI タスクを開始する。実行中の場合は開始せず False を返す。"""
        if self._is_running:
            return False

        self._reset_for_run(initial_callback, part_callback, finish_callback)
        background_tasks.create(
            helpers.await_with_context(
                self._run_command(args, cd, input_json),
                self.client,  # type: ignore[arg-type]
            ),
            name="xterm_view_run",
        )
        return True

    def stop(self) -> None:
        """実行中の CLI タスクに終了を要求する。"""
        if self._process and self._is_running:
            self._cancelled = True
            self._process.terminate()

    def _reset_for_run(
        self,
        initial_callback: Callable[[int], None] | None,
        part_callback: Callable[[dict], None] | None,
        finish_callback: Callable[[bool], None] | None,
    ) -> None:
        """次の実行に向けて状態と端末表示を初期化する。"""
        self._terminal.write(b"\x1bc")
        self._cancelled = False
        self._success = False
        self._total_count = 0
        self._part_count = 0
        self._progress.props("max=1")
        self._progress.value = 0
        self._progress.set_visibility(False)
        self._initial_callback = initial_callback
        self._part_callback = part_callback
        self._finish_callback = finish_callback

    async def _run_command(self, args: list[str], cd: str, input_json: Any) -> None:
        """コマンドを実行して xterm にストリーミングする。"""
        self._is_running = True
        success = False

        try:
            stdin_data = json.dumps(input_json).encode() if input_json is not None else None
            self._process = subprocess.Popen(
                args,
                cwd=cd,
                stdin=subprocess.PIPE if stdin_data is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if stdin_data is not None:
                await asyncio.to_thread(self._process.stdin.write, stdin_data)  # type: ignore[union-attr]
                self._process.stdin.close()  # type: ignore[union-attr]

            await asyncio.gather(
                self._read_stdout(),
                self._read_stderr(),
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
            self._terminal.write(f"\r\n[エラー] {type(e).__name__}: {e}\r\n".encode())
        finally:
            self._is_running = False
            self._process = None
            self._success = success
            self._progress.set_visibility(False)
            if self._finish_callback:
                self._finish_callback(self._success)

    async def _read_stdout(self) -> None:
        """stdout を行単位で読み、マーカー間の JSON をコールバックに渡す。"""
        json_buf: list[str] = []
        block_type = ""
        while True:
            line_bytes = await asyncio.to_thread(self._process.stdout.readline)  # type: ignore[union-attr]
            if not line_bytes:
                break
            line = line_bytes.decode(errors="replace").rstrip("\r\n")
            if line == INITIAL_RESULT_START:
                block_type = "initial"
                json_buf = []
                continue
            if line == PART_RESULT_START:
                block_type = "part"
                json_buf = []
                continue
            if line in (INITIAL_RESULT_END, PART_RESULT_END):
                self._handle_json_block(block_type, json_buf)
                json_buf = []
                block_type = ""
                continue
            if block_type:
                json_buf.append(line)
            else:
                self._terminal.write((line + "\r\n").encode())

    async def _read_stderr(self) -> None:
        """stderr をバイト列のまま xterm に表示する。"""
        while True:
            chunk = await asyncio.to_thread(self._process.stderr.read, 128)  # type: ignore[union-attr]
            if not chunk:
                break
            self._terminal.write(chunk)

    def _handle_json_block(self, block_type: str, json_buf: list[str]) -> None:
        """CLI タスクのマーカー JSON を処理する。"""
        try:
            data = json.loads("\n".join(json_buf))
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
