from pathlib import Path
from typing import cast
from nicegui import ui
from common.setting import cnfg
import sys
from edit.edit_app_ctx import EditCtx
from common.wavesurfer import simple_player


def tab_main(ctx: EditCtx):

    # ═══════════════════════════════════════════════════════════════════════════════
    # ファイル一覧
    # ═══════════════════════════════════════════════════════════════════════════════

    ws = simple_player("ws_02", visible=False, autoplay=True)
    def play_src(path: str):
        ws.container.set_visibility(True)
        ws.ws.load(path)

    with ui.row().classes("w-full gap-4 items-start"):
        with ui.column().classes("flex-1 gap-1"):
            ui.label("書き出しフォルダ").classes("font-bold")
            ctx.table = ui.table(
                columns=[
                    {
                        "label": "",
                        "field": "path",
                        "name": "expand",
                        "style": "width: 30px",
                    },
                    {
                        "label": "",
                        "field": "path",
                        "name": "play",
                        "style": "width: 30px",
                    },
                    {
                        "label": "Name",
                        "field": "name",
                        "name": "name",
                        "align": "left",
                    },
                ],
                rows=[],
                selection="multiple",
                row_key="path",
            ).classes("h-120 w-full no-shadow brdr q-pa-none")
            with ctx.table.add_slot('body-cell-play'):
                with ctx.table.cell('play'):
                    ui.button(icon="play_circle").props('flat').on(
                        'click',
                        js_handler='() => emit(props.value)',
                        handler=lambda e: play_src(e.args),
                    ).style('padding: 2px 4px;')
            with ctx.table.add_slot("body-cell-expand"):
                with ctx.table.cell("expand"):
                    ui.button().props(
                        'flat'
                        ' :icon="props.expand ? \'expand_less\' : \'expand_more\'"'
                        ' :style="props.row.is_expandable ? \'padding: 2px 4px\' : \'padding: 2px 4px; display: none\'"'
                    ).on(
                        "click",
                        js_handler="() => { props.expand = !props.expand; emit({ value: props.value, expand: props.expand }) }",
                        handler=lambda e: print(e.args),
                    )
        with ui.column().classes("flex-1 gap-1"):
            ui.label("エディットプール").classes("font-bold")
            ctx.pool_table = ui.table(
                columns=[

                    {
                        "label": "",
                        "field": "path",
                        "name": "play",
                        "style": "width: 30px",
                    },
                    {
                        "label": "Name",
                        "field": "name",
                        "name": "name",
                        "align": "left",
                    },
                ],
                rows=[],
                selection="multiple",
                row_key="path",
            ).classes("h-120 w-full no-shadow brdr q-pa-none")
            with ctx.pool_table.add_slot("body-cell-play"):
                with ctx.pool_table.cell("play"):
                    ui.button(icon="play_circle").props('flat').on(
                        'click',
                        js_handler='() => emit(props.value)',
                        handler=lambda e: play_src(e.args),
                    ).style('padding: 2px 4px;')
    ctx.load_files(str(cnfg.outputs_dir))
    ctx.load_pool()
