from nicegui import ui

from common.worker import Worker
from testpage.testpage_ctx import TestCtx
from testpage.testpage_main_tab import tab_main
from testpage.testpage_02_tab import tab_02
from music.music_app_ctx import MusicCtx
from common.wavesurfer import setup_wavesurfer

def main_page(worker: Worker):
    setup_wavesurfer()

    ctx = TestCtx(worker)
    mctx = MusicCtx(worker)

    ui.markdown("""# dataset-ui-music
ここはテストページです""")

    with ui.tabs().classes("w-full").classes("text-dark").props(
        'inline-label align="left"'
    ) as tabs:
        main_Tab = ui.tab("main", label="メイン", icon="music_note")
        t02_Tab = ui.tab("02", label="テスト02", icon="music_note")
    with ui.tab_panels(tabs, animated=False, value=main_Tab).classes("w-full"):
        with ui.tab_panel(main_Tab):
            tab_main(ctx)
        with ui.tab_panel(t02_Tab):
            tab_02(ctx, mctx)
