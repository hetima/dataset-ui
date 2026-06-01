from nicegui import ui

from common.wavesurfer import setup_wavesurfer
from edit.edit_main_tab import tab_main
from edit.edit_setting_tab import tab_setting
from edit.edit_compi_tab import tab_compi
from edit.edit_app_ctx import EditCtx

def main_page():
    setup_wavesurfer()
    ctx = EditCtx()

    ui.markdown("""# dataset-ui-edit
音声ファイルのメタデータを書き出す webui です""")

    with ui.tabs().classes("w-full").classes("text-dark").props(
        'inline-label align="left"'
    ) as ctx.tabs:
        main_Tab = ui.tab("main", label="メイン", icon="home")
        compi_tab = ui.tab("compi", label="コンピング", icon="music_note")
        setting_tab = ui.tab("setting", label="設定", icon="settings")
    with ui.tab_panels(ctx.tabs, animated=False, value=main_Tab).classes("w-full"):
        with ui.tab_panel(main_Tab):
            tab_main(ctx)
        with ui.tab_panel(compi_tab):
            tab_compi(ctx)
        with ui.tab_panel(setting_tab):
            tab_setting(ctx)
