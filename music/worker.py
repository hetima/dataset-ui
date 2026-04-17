import asyncio
import time
import traceback
from collections.abc import Callable, Generator
from multiprocessing import Event, Manager, Process
from queue import Empty, Queue
from typing import TypeVar
from threading import Event as EventClass
from nicegui import app, background_tasks, binding, ui

T = TypeVar("T")

PROGRESS = "progress"
STATUS = "status"
PROGRESS_RESULT = "prgr"

def _run_generator(
    func: Callable[..., Generator[tuple[float, str, dict|None], None, T]],
    queue: Queue,
    stop_event: EventClass,
    data,
) -> None:
    try:
        gen = func(data, stop_event)
        while True:
            try:
                progress, status, progress_result = next(gen)
                queue.put({PROGRESS: progress, STATUS: status, PROGRESS_RESULT: progress_result})
            except StopIteration as e:
                queue.put({PROGRESS: 2.0, STATUS: "完了", "result": e.value})
                break
    except Exception:
        traceback.print_exc()
        try:
            queue.put({PROGRESS: 2.0, STATUS: "エラー"})
        except Exception:
            pass


class Worker:
    is_running = binding.BindableProperty()
    can_run = binding.BindableProperty()
    progress = binding.BindableProperty()
    result = binding.BindableProperty()
    status = binding.BindableProperty()
    elapsed_time = binding.BindableProperty()

    def __init__(self) -> None:
        self._queue: Queue
        self._stop_event: EventClass
        self._process: Process | None = None
        self.progress = 0.0
        self.is_running = False
        self.can_run = True
        self.result = None
        self.status = ""
        self.elapsed_time = "00:00:00"
        self._on_complete: Callable[..., None] | None = None
        app.on_startup(self._create_queue)

    async def run(
        self,
        func: Callable[..., Generator[tuple[float, str, dict|None], None, T]],
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
        self.elapsed_time = "00:00:00"
        _start_time = time.perf_counter()
        _last_seconds = 0
        self.is_running = True
        self.can_run = False
        self.progress = 0.0
        self.status = ""
        self._stop_event.clear()
        while self.progress < 2.0:
            try:
                msg = self._queue.get_nowait()
            except Empty:
                await asyncio.sleep(0.1)
                elapsed_time = int(time.perf_counter() - _start_time)
                if _last_seconds != elapsed_time:
                    minutes, seconds = divmod(elapsed_time, 60)
                    hours, minutes = divmod(minutes, 60)
                    self.elapsed_time = f"{hours:02}:{minutes:02}:{seconds:02}"
                    _last_seconds = elapsed_time
                if self._process is not None and not self._process.is_alive():
                    break
                continue
            self.progress = msg.get(PROGRESS, "")
            self.status = msg.get(STATUS, "")
            prgr = msg.get(PROGRESS_RESULT, None)
            if prgr != None and self._on_complete != None:
                self._on_complete(prgr)
            
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
        print(f"total time: {self.elapsed_time}")
        self.elapsed_time = "00:00:00"

    def request_cancel(self) -> None:
        ui.notify("停止要求をしました")
        self._stop_event.set()

    def terminate_now(self) -> None:
        self._stop_event.set()
        if self._process is not None and self._process.is_alive():
            self._process.terminate()
