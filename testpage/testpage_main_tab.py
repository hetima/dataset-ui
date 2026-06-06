import sys
from pathlib import Path
from nicegui import ui

from testpage.testpage_ctx import TestCtx
from common.xterm_dialog import XtermDialog


def tab_main(_ctx: TestCtx):
    ui.label("test")

    def run_xterm_test():
        cli = str(Path(__file__).parent / "cli_task_xtermtest.py")
        XtermDialog(
            args=[sys.executable, cli],
            title="環境変数テスト",
        ).open()

    ui.button("環境変数テスト", on_click=run_xterm_test)
