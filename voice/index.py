from nicegui import ui

from common.wavesurfer import setup_wavesurfer
from voice.voice_app_ctx import VoiceCtx
from voice.voice_main_tab import tab_main
from voice.voice_setting_tab import tab_setting
from voice.irodori_train_tab import tab_iridori_train

def main_page():
    setup_wavesurfer()
    ctx = VoiceCtx()

    ui.markdown("""# dataset-ui-voice""")

    with ui.tabs().classes("w-full").classes("text-dark").props(
        'inline-label align="left"'
    ) as tabs:
        main_Tab = ui.tab("main", label="メイン", icon="headset_mic")
        iridori_train_Tab = ui.tab(
            "iridori_train", label="Irodori Train", icon="source"
        )
        setting_tab = ui.tab("setting", label="設定", icon="settings")
    with ui.tab_panels(tabs, animated=False, value=main_Tab).classes("w-full"):
        with ui.tab_panel(main_Tab):
            tab_main(ctx)
        with ui.tab_panel(iridori_train_Tab):
            tab_iridori_train(ctx)
        with ui.tab_panel(setting_tab):
            tab_setting(ctx)
