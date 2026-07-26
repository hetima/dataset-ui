from pathlib import Path
from nicegui import binding, ui
from common.setting import cnfg
from ying_music_svc.ying_app_ctx import YingCtx

def tab_setting(ctx: YingCtx):
    # ═══════════════════════════════════════════════════════════════════════════════
    # リポジトリパス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("リポジトリパス", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("リポジトリのフォルダパスを入力してください")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            repository_path_input = ui.input(
                value=str(cnfg.ying.repository_dir),
                label="repository path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button(
                "保存",
                on_click=lambda: ctx.set_repository_dir(repository_path_input.value),
            )

    # ═══════════════════════════════════════════════════════════════════════════════
    # venvパス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("venvパス", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("venvのパスを入力してください。リポジトリ内、あるいは一階層上の「.venv」は自動認識されるので空白のままで大丈夫です。")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            venv_dir_input = ui.input(
                value=str(cnfg.ying.venv_dir),
                label="models root path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button(
                "保存",
                on_click=lambda: ctx.set_venv_dir(venv_dir_input.value),
            )

