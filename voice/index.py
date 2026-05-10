from nicegui import ui


from common.worker import Worker
from voice.voice_app_ctx import VoiceCtx
from voice.voice_main_tab import tab_main
from voice.voice_setting_tab import tab_setting

def main_page(worker: Worker):
    ctx = VoiceCtx(worker)

    ui.markdown("""# dataset-ui-voice
音声ファイルのメタデータを書き出す webui です""")

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
