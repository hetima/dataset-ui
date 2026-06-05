from nicegui import ui


from music.music_app_ctx import MusicCtx
from music.music_main_tab import tab_main
from music.music_setting_tab import tab_setting

def main_page():
    ctx = MusicCtx()

    ui.markdown("""# dataset-ui-music""")

    with ui.tabs().classes("w-full").classes("text-dark").props(
        'inline-label align="left"'
    ) as tabs:
        main_Tab = ui.tab("main", label="メイン", icon="music_note")
        setting_tab = ui.tab("setting", label="設定", icon="settings")
    with ui.tab_panels(tabs, animated=False, value=main_Tab).classes("w-full"):
        with ui.tab_panel(main_Tab):
            tab_main(ctx)
        with ui.tab_panel(setting_tab):
            tab_setting(ctx)
