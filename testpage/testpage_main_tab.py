from nicegui import ui

from testpage.testpage_ctx import TestCtx


def tab_main(ctx: TestCtx):

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
