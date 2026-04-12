import asyncio
import os
from collections.abc import Callable, Generator
from multiprocessing import Manager
from queue import Empty, Queue

# from multiprocessing import Event
from threading import Event
from typing import TypeVar

from nicegui import app, background_tasks, binding, run, ui

T = TypeVar("T")


class Worker:
    is_running = binding.BindableProperty()
    can_run = binding.BindableProperty()
    progress = binding.BindableProperty()
    result = binding.BindableProperty()
    status = binding.BindableProperty()

    def __init__(self) -> None:
        # self._manager: Manager
        self._queue: Queue
        self._stop_event: Event
        self.progress = 0.0
        self.is_running = False
        self.can_run = True
        self.result = None
        self.status = ""
        self._on_complete: Callable[..., None] | None = None
        app.on_startup(self._create_queue)

    async def run(
        self,
        func: Callable[..., Generator[tuple[float, str], None, T]],
        data,
        on_complete: Callable[[T], None] | None = None,
    ) -> None:
        if self.is_running:
            ui.notify(f"他の処理が実行中です", type="negative")
            return
        self._on_complete = on_complete
        background_tasks.create(
            run.cpu_bound(
                self._run_generator, func, self._queue, self._stop_event, data
            )
        )
        background_tasks.create(self._consume_queue())
        self.is_running = True
        self.can_run = False
        self.progress = 0.0
        self.result = None
        self.status = ""

    @staticmethod
    def _run_generator(
        func: Callable[..., Generator[tuple[float, str], None, T]],
        queue: Queue,
        stop_event,
        data,
    ) -> None:
        gen = func(data, stop_event)
        while True:
            try:
                progress, status = next(gen)
                queue.put({"progress": progress, "status": status})
            except StopIteration as e:
                queue.put({"progress": 2.0, "status": "完了", "result": e.value})
                break

    def _create_queue(self) -> None:
        m = Manager()
        self._queue = m.Queue(maxsize=1)
        self._stop_event = m.Event()

    async def _consume_queue(self) -> None:
        self.is_running = True
        self.can_run = False
        self.progress = 0.0
        self.status = ""
        self._stop_event.clear()
        # 2回 {'progress': 1.0} すると前の処理が残る
        # self._queue.get()
        while self.progress < 2.0:
            try:
                msg = self._queue.get_nowait()
            except Empty:
                await asyncio.sleep(0.3)
                continue
            self.progress = msg["progress"]
            self.status = msg.get("status", "")
            if "result" in msg:
                if (not self._stop_event.is_set()):
                    self.result = msg["result"]
                    if self._on_complete is not None:
                        self._on_complete(self.result)
                break
        self.is_running = False
        self.can_run = True
        self._stop_event.clear()
        self.status = ""

    def request_cancel(self) -> None:
        ui.notify(f"停止要求をしました")
        self._stop_event.set()
