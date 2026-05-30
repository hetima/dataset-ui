from nicegui import binding, ui
from nicegui.elements.table import Table

from common.worker import Worker


@binding.bindable_dataclass
class TestCtx:
    def __init__(self, worker: Worker):
        self.files = []
        self.table: Table
        self.worker: Worker = worker
        self.client = ui.context.client

    def notify(self, text: str, type=None):
        with self.client:
            ui.notify(text, type=type)

    def target_files(self) -> list:
        return self.table.selected
