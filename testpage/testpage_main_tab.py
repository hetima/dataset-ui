import sys
from pathlib import Path
from nicegui import ui

from testpage.testpage_ctx import TestCtx
from common.xterm_dialog import XtermDialog


def tab_main(ctx: TestCtx):

    # ═══════════════════════════════════════════════════════════════════════════════
    # XtermDialog テスト
    # ═══════════════════════════════════════════════════════════════════════════════

    def open_xterm():
        script = str(Path(__file__).parent / "xtermtest.py")
        dlg = XtermDialog(
            args=[sys.executable, script],
            title="XtermDialog テスト",
        )
        dlg.open()

    ui.button("XtermDialog テスト", on_click=open_xterm)

    # ═══════════════════════════════════════════════════════════════════════════════
    # ファイル一覧
    # ═══════════════════════════════════════════════════════════════════════════════

    ctx.table = ui.table(
        columns=[
            {"label": "Name", "field": "name", "name": "name", "align": "left"},
        ],
        rows=[],
        selection="multiple",
        row_key="name",
    ).classes("h-120 w-full no-shadow brdr q-pa-none")
