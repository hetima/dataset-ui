import sys
from pathlib import Path
from nicegui import ui

from testpage.testpage_ctx import TestCtx
from common.xterm_dialog import XtermDialog
from music.music_app_ctx import MusicCtx
from common.setting import cnfg
from common.wavesurfer import WaveSurferWidget, simple_player

def tab_02(tctx: TestCtx, ctx: MusicCtx):

    # ═══════════════════════════════════════════════════════════════════════════════
    # Load files
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.row().classes("items-center gap-2"):
        dataset_dropdown = (
            ui.dropdown_button(icon="folder", auto_close=True)
            .props("outline")
            .style("padding: 4px 8px;")
        )
        path_input = (
            ui.input(
                value=cnfg.music.last_dataset_path,
                label="dataset path",
                placeholder="フォルダのパスを入力...",
                on_change=lambda e: setattr(e.sender, "value", e.value),
            )
            .props('style="min-width: 500px" outlined clearable')
            .classes("w-140")
        )
        ui.button("読み込み", on_click=lambda: ctx.load_files(path_input.value))

    # ═══════════════════════════════════════════════════════════════════════════════
    # ファイル一覧
    # ═══════════════════════════════════════════════════════════════════════════════

    # ws = WaveSurferWidget("ws_02")
    # with ui.column().classes("items-start gap-0"):
    #     ws.build()
    #     with ui.row().classes("items-center gap-0"):
    #         ui.button(icon="play_arrow").props("flat").on(
    #             "click", js_handler=ws.play_js()
    #         ).style("padding: 2px 4px;")
    #         ui.button(icon="pause").props("flat").on(
    #             "click", js_handler=ws.pause_js()
    #         ).style("padding: 2px 4px;")
    #         play_info = ui.label("")
    #         ws.duration_label().style("margin:0 0 0 10px")
    #         ui.slider(min=0, max=1, step=0.05, value=1).style(
    #             "width: 120px; margin:0 0 0 20px"
    #         ).on(
    #             "update:model-value",
    #             js_handler=f"(v) => window['{ws._name}'] && window['{ws._name}'].setVolume(v)",
    #         )

    ws = simple_player("ws_03", visible=False)
    def play_src(path: str):
        ws.container.set_visibility(True)
        ws.ws.load(path)

    ctx.table = ui.table(
        columns=[
            {"label": "", "field": "path", "name": "expand", "style": "width: 30px"},
            {"label": "", "field": "path", "name": "play", "style": "width: 30px"},
            {
                "label": "Name",
                "field": "name",
                "name": "name",
                "align": "left",
            },
            {
                "name": "caption",
                "field": "caption",
                "label": "Caption",
                "style": "white-space: nowrap; overflow: hidden;text-overflow: ellipsis; min-width:100px; max-width:160px",
                "align": "left",
            },
            {
                "name": "lyrics",
                "field": "lyrics",
                "label": "Lyrics",
                "style": "white-space: nowrap; overflow: hidden;text-overflow: ellipsis; min-width:100px; max-width:160px",
                "align": "left",
            },
            {
                "label": "Lang",
                "field": "language",
                "editable": True,
                "style": "width: 80px",
                "name": "language",
                "align": "left",
            },
            {
                "label": "BPM",
                "field": "bpm",
                "editable": True,
                "name": "bpm",
                "style": "width: 80px",
                "align": "left",
            },
            {
                "label": "KEY",
                "field": "keyscale",
                "editable": True,
                "name": "keyscale",
                "style": "width: 80px",
                "align": "left",
            },
            {
                "label": "Timesig",
                "field": "timesignature",
                "editable": True,
                "name": "timesignature",
                "style": "width: 80px",
                "align": "left",
            },
            {
                "label": "Duration",
                "field": "duration",
                "editable": True,
                "name": "duration",
                "style": "width: 80px",
                "align": "left",
            },
        ],
        rows=[],
        selection="multiple",
        row_key="name",
    ).classes("h-120 w-full no-shadow brdr q-pa-none")
    with ctx.table.add_slot("body-cell-play"):
        with ctx.table.cell("play"):
            ui.button(icon="play_circle").props("flat").on(
                "click",
                js_handler="() => emit(props.value)",
                handler=lambda e: play_src(e.args),
            ).style("padding: 2px 4px;")
    with ctx.table.add_slot("body-cell-expand"):
        with ctx.table.cell("expand"):
            ui.button().props(
                "flat"
                " :icon=\"props.expand ? 'expand_less' : 'expand_more'\""
                " :style=\"props.row.is_expandable ? 'padding: 2px 4px' : 'padding: 2px 4px; display: none'\""
            ).on(
                "click",
                js_handler="() => { props.expand = !props.expand; emit({ value: props.value, expand: props.expand }) }",
                handler=lambda e: print(e.args),
            )
