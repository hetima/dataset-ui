from pathlib import Path
from nicegui import binding, ui
from common.setting import cnfg
from edit.edit_app_ctx import EditCtx


def tab_setting(ctx: EditCtx):
    # ═══════════════════════════════════════════════════════════════════════════════
    # 出力パス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("書き出しパス", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("成果物を書き出すフォルダパスを入力してください")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            outputs_path_input = ui.input(
                value=str(cnfg.outputs_dir),
                label="outputs path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button(
                "保存",
                on_click=lambda: ctx.set_outputs_dir(outputs_path_input.value),
            )

    # ═══════════════════════════════════════════════════════════════════════════════
    # モデルパス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("モデルパス", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("モデルをダウンロードするフォルダパスを入力してください")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            model_root_path_input = ui.input(
                value=str(cnfg.models_dir),
                label="models root path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button(
                "保存",
                on_click=lambda: ctx.set_models_root(model_root_path_input.value),
            )
