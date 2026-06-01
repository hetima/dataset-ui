from nicegui import ui

from common.wavesurfer import setup_wavesurfer, setup_multitrack
from edit.edit_main_tab import tab_main
from edit.edit_setting_tab import tab_setting
from edit.edit_compi_tab import tab_compi
from edit.edit_daw_tab import tab_main as tab_daw
from edit.edit_app_ctx import EditCtx

def main_page():
    setup_wavesurfer()
    setup_multitrack()
    ctx = EditCtx()

    ui.markdown("""# dataset-ui-edit
音声ファイルのメタデータを書き出す webui です""")

    with ui.tabs().classes("w-full").classes("text-dark").props(
        'inline-label align="left"'
    ) as ctx.tabs:
        main_Tab = ui.tab("main", label="メイン", icon="home")
        daw_tab = ui.tab("daw", label="DAW", icon="graphic_eq")
        setting_tab = ui.tab("setting", label="設定", icon="settings")
    with ui.tab_panels(ctx.tabs, animated=False, value=main_Tab).classes("w-full").props("keep-alive"):
        with ui.tab_panel(main_Tab):
            tab_main(ctx)
        with ui.tab_panel(daw_tab):
            tab_daw(ctx)
        with ui.tab_panel(setting_tab):
            tab_setting(ctx)
