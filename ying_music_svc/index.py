from nicegui import ui

from ying_music_svc.ying_app_ctx import YingCtx
from ying_music_svc.ying_main_tab import tab_main
from ying_music_svc.ying_setting_tab import tab_setting

def main_page():
    ctx = YingCtx()

    ui.markdown("""# dataset-ui YingMusic-SVC
YingMusic-SVC""")

    with ui.tabs().classes("w-full").classes("text-dark").props(
        'inline-label align="left"'
    ) as tabs:
        main_Tab = ui.tab("main", label="メイン", icon="apps")
        setting_tab = ui.tab("setting", label="設定", icon="settings")
    with ui.tab_panels(tabs, animated=False, value=main_Tab).classes("w-full"):
        with ui.tab_panel(main_Tab):
            tab_main(ctx)
        with ui.tab_panel(setting_tab):
            tab_setting(ctx)