from nicegui import ui


from common.worker import Worker
from testpage.testpage_ctx import TestCtx
from testpage.testpage_main_tab import tab_main

def main_page(worker: Worker):
    ctx = TestCtx(worker)
    
    ui.markdown("""# dataset-ui-music
ここはテストページです""")

    with ui.tabs().classes("w-full").classes("text-dark").props(
        'inline-label align="left"'
    ) as tabs:
        main_Tab = ui.tab("main", label="メイン", icon="music_note")
    with ui.tab_panels(tabs, animated=False, value=main_Tab).classes("w-full"):
        with ui.tab_panel(main_Tab):
            tab_main(ctx)
