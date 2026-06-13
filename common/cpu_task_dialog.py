import multiprocessing
import multiprocessing.queues
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable
from nicegui import ui, background_tasks, helpers

from common.xterm_dialog import xterm_option

# ワーカー関数のシグネチャ:
#   def my_task(data: Any, queue: multiprocessing.Queue, stop_event: multiprocessing.Event) -> Any
#
# queue に送るメッセージ:
#   {"type": "log", "text": "..."}          → xterm に表示
#   {"type": "progress", "value": N}        → プログレスバー更新
#   {"type": "progress", "value": N, "max": M} → max も更新
#
# キャンセル確認: stop_event.is_set() を定期的にチェックして None を return する

_POLL_INTERVAL = 0.05  # キューポーリング間隔（秒）
_CANCEL_TIMEOUT = 10   # キャンセル後の強制終了までの待機時間（秒）


def _worker_wrapper(fn, data, queue, stop_event):
    """ProcessPoolExecutor から呼ばれるラッパー（pickle のためモジュールレベルに置く）"""
    try:
        return fn(data, queue, stop_event)
    except Exception as e:
        queue.put({"type": "log", "text": f"[エラー] {type(e).__name__}: {e}"})
        return None


class CpuTaskDialog(ui.dialog):
    """run.cpu_bound の代替: ProcessPoolExecutor + Queue で進捗をリアルタイム表示するダイアログ"""

    def __init__(
        self,
        fn: Callable,
        data: Any = None,
        title: str = "",
        finish_callback: Callable[[bool, Any], None] | None = None,
    ) -> None:
        super().__init__()
        self.props("persistent")
        self._fn = fn
        self._data = data
        self.title = title
        self._finish_callback = finish_callback

        self._is_running = False
        self._cancel_requested = False
        self._result: Any = None
        self._success = False
        self._closed = False  # _safe_close の多重呼び出し・削除済み状態をガード

        self._manager: multiprocessing.Manager | None = None  # type: ignore[type-arg]
        self._queue: multiprocessing.queues.Queue | None = None  # type: ignore[type-arg]
        self._stop_event = None
        self._executor: ProcessPoolExecutor | None = None

        self._show_panel()

    def _handle_value_change(self, value) -> None:
        """実行中は ESC / 背景クリックによるダイアログ閉じを禁止"""
        if not value and self._is_running:
            self.open()
            return
        super()._handle_value_change(value)

    def _show_panel(self):
        self.style("max-width: none")
        with self, ui.card().style("width: fit-content; max-width: 95vw"):
            ui.label(self.title).classes("text-sm")
            self._terminal = ui.xterm(xterm_option).classes("dialog-xterm")
            with ui.row().classes("w-full justify-end items-center"):
                self._progress = (
                    ui.circular_progress(min=0, max=1, value=0, size="30px")
                    .props("instant-feedback")
                )
                self._progress.set_visibility(False)
                self._stop_btn = ui.button("停止", on_click=self._request_cancel)
                self._stop_btn.set_enabled(False)
                self._close_btn = ui.button("閉じる", on_click=self._safe_close)
                self._close_btn.set_enabled(False)

        background_tasks.create(
            helpers.await_with_context(self._run(), self.client),  # type: ignore[arg-type]
            name="cpu_task_run",
        )

    async def _run(self):
        import asyncio

        self._is_running = True
        self._cancel_requested = False
        self._stop_btn.set_enabled(True)

        # Manager は spawn コンテキストで Queue/Event を共有するために必要
        self._manager = multiprocessing.Manager()
        self._queue = self._manager.Queue() # type: ignore
        self._stop_event = self._manager.Event() # type: ignore

        self._executor = ProcessPoolExecutor(max_workers=1)
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            self._executor,
            _worker_wrapper,
            self._fn,
            self._data,
            self._queue,
            self._stop_event,
        )

        try:
            while not future.done():
                self._drain_queue()
                await asyncio.sleep(_POLL_INTERVAL)
            self._drain_queue()

            if self._cancel_requested:
                self._terminal.write("\r\n[キャンセルされました]\r\n".encode())
            else:
                self._result = future.result()
                self._success = True
                self._terminal.write("\r\n[完了]\r\n".encode())

        except asyncio.CancelledError:
            self._terminal.write("\r\n[キャンセルされました(タスク)]\r\n".encode())
        except Exception as e:
            self._terminal.write(f"\r\n[エラー] {type(e).__name__}: {e}\r\n".encode())
        finally:
            self._cleanup()

    def _drain_queue(self):
        """キューに溜まったメッセージをすべて処理"""
        while self._queue and not self._queue.empty():
            try:
                msg = self._queue.get_nowait()
            except Exception:
                break
            t = msg.get("type")
            if t == "log":
                text = msg.get("text", "")
                self._terminal.write((text + "\r\n").encode())
            elif t == "progress":
                if "max" in msg:
                    self._progress.props(f"max={msg['max']}")
                    self._progress.set_visibility(True)
                self._progress.value = msg.get("value", 0)

    def _cleanup(self):
        self._is_running = False
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None
        if self._manager:
            self._manager.shutdown()
            self._manager = None
        self._queue = None
        self._stop_event = None
        self._progress.set_visibility(False)
        self._stop_btn.set_enabled(False)
        self._close_btn.set_enabled(True)

    def _request_cancel(self):
        """キャンセルをリクエストし、ワーカーが止まるのを待つ"""
        if not self._is_running:
            return
        self._cancel_requested = True
        self._stop_btn.set_enabled(False)
        self._terminal.write("\r\n[停止を要求しました...]\r\n".encode())
        if self._stop_event:
            self._stop_event.set()
        # タイムアウト後の強制終了は _executor.shutdown(cancel_futures=True) に委ねる
        if self._executor:
            background_tasks.create(self._force_kill_after_timeout(), name="cpu_task_force_kill")

    async def _force_kill_after_timeout(self):
        import asyncio
        await asyncio.sleep(_CANCEL_TIMEOUT)
        if self._is_running and self._executor:
            self._terminal.write("\r\n[タイムアウト: 強制終了します]\r\n".encode())
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _safe_close(self):
        if self._closed:
            return
        self._closed = True
        if self._finish_callback:
            self._finish_callback(self._success, self._result)
        # 親スロットが既に破棄されている場合は delete() が ValueError を投げるためガード
        try:
            self.delete()
        except (ValueError, RuntimeError):
            pass
