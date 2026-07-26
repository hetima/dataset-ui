from nicegui import binding, ui
from nicegui.elements.table import Table

from common.setting import cnfg


@binding.bindable_dataclass
class YingCtx:
    def __init__(self):
        self.files = []
        self.table: Table
        self.client = ui.context.client

    def notify(self, text: str, type=None):
        with self.client:
            ui.notify(text, type=type)

    def set_repository_dir(self, path: str | None) -> None:
        cnfg.ying.set_repository_dir(path or "")
        self.notify("リポジトリパスを保存しました")

    def set_venv_dir(self, path: str | None) -> None:
        cnfg.ying.set_venv_dir(path or "")
        self.notify("venvパスを保存しました")


