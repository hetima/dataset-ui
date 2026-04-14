import asyncio
import traceback
from collections.abc import Callable, Generator
from multiprocessing import Event, Manager, Process
from queue import Empty, Queue
from typing import TypeVar
from threading import Event as EventClass
from nicegui import app, background_tasks, binding, ui

T = TypeVar("T")


def _run_generator(
    func: Callable[..., Generator[tuple[float, str], None, T]],
    queue: Queue,
    stop_event: EventClass,
    data,
) -> None:
    try:
        gen = func(data, stop_event)
        while True:
            try:
                progress, status = next(gen)
                queue.put({"progress": progress, "status": status})
            except StopIteration as e:
                queue.put({"progress": 2.0, "status": "完了", "result": e.value})
                break
    except Exception:
        traceback.print_exc()
        try:
            queue.put({"progress": 2.0, "status": "エラー"})
        except Exception:
            pass


class Worker:
    is_running = binding.BindableProperty()
    can_run = binding.BindableProperty()
    progress = binding.BindableProperty()
    result = binding.BindableProperty()
    status = binding.BindableProperty()

    def __init__(self) -> None:
        self._queue: Queue
        self._stop_event: EventClass
        self._process: Process | None = None
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
            ui.notify("他の処理が実行中です", type="negative")
            return
        self._on_complete = on_complete
        self._process = Process(
            target=_run_generator,
            args=(func, self._queue, self._stop_event, data),
        )
        self._process.start()
        background_tasks.create(self._consume_queue())
        self.is_running = True
        self.can_run = False
        self.progress = 0.0
        self.result = None
        self.status = ""

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
        while self.progress < 2.0:
            try:
                msg = self._queue.get_nowait()
            except Empty:
                await asyncio.sleep(0.3)
                if self._process is not None and not self._process.is_alive():
                    break
                continue
            self.progress = msg["progress"]
            self.status = msg.get("status", "")
            if "result" in msg:
                if not self._stop_event.is_set():
                    self.result = msg["result"]
                    if self._on_complete is not None:
                        self._on_complete(self.result)
                break
        if self._process is not None:
            self._process.join(timeout=10)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=5)
            self._process = None
        self.is_running = False
        self.can_run = True
        self._stop_event.clear()
        self.status = ""

    def request_cancel(self) -> None:
        ui.notify("停止要求をしました")
        self._stop_event.set()
