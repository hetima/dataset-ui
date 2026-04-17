import argparse
from pathlib import Path
from typing import cast

from nicegui import ui
from nicegui.elements.table import Table
from music.setting import cnfg
from music.musicfile import MusicFile
from music.worker import Worker
from music.app_ctx import MusicCtx
from music.tab_main import tab_main
from music.tab_setting import tab_setting


_worker: Worker = Worker()

@ui.page("/")
def main_page():
    ctx = MusicCtx(_worker)
    ui.query('body').style('font-family: Roboto, "BIZ UDPGothic", "BIZ UDPゴシック", sans-serif;')

    ui.add_css('''
.infotxt {
    color: #666;
}
.q-table th, .q-table td, .padd2 {
    padding: 2px 2px;
    min-height: 20px;
    height: auto;
}

.padd4 {
    padding: 4px 4px;
    min-height: 20px;
}
.padd8 {
    padding: 8px 8px;
    min-height: 24px;
}

.brdr {
    border: 1px solid #ccc;
}

.q-checkbox__inner {
    font-size: 34px;
}
''')
    ui.colors(secondary='#747474')
    ui.markdown("""## dataset-ui-music
ACE-Step 向けのメタデータを書き出す webui です""")

    with ui.tabs().classes('w-full').classes("text-dark").props('inline-label align="left"') as tabs:
        main_Tab = ui.tab('main',label="メイン", icon="music_note")
        setting_tab = ui.tab('setting',label="設定", icon="settings")
    with ui.tab_panels(tabs, animated=False, value=main_Tab).classes('w-full'):
        with ui.tab_panel(main_Tab):
            tab_main(ctx)
        with ui.tab_panel(setting_tab):
            tab_setting(ctx)
            
    # ═══════════════════════════════════════════════════════════════════════════════
    # 処理中UI
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.footer(bordered=True).bind_visibility_from(ctx.worker, "is_running").style('background-color: #f2f2f2'):
        with ui.row().classes("items-center gap-4"):
            ui.spinner(size='lg')
            with ui.column():
                with ui.row().classes("items-center gap-4"):
                    ui.label("バックグラウンド処理を実行しています").style('color: #010101')
                    ui.label("").style('color: #010101').bind_text_from(ctx.worker, "elapsed_time")
                with ui.row().classes("items-center gap-4"):
                    ui.button("処理を中止する", on_click=ctx.worker.request_cancel).bind_visibility_from(
                        ctx.worker, "is_running"
                    ).props('color="orange"').tooltip("現在の処理が済んだら終了")
                    ui.button("処理を強制終了する", icon='warning', on_click=ctx.worker.terminate_now).bind_visibility_from(
                        ctx.worker, "is_running"
                    ).props('color="red"').tooltip("強制的に子プロセスを終了")
                    ui.label().style('color: #010101').bind_text_from(ctx.worker, "status")
        ui.linear_progress(show_value=False).props("instant-feedback").bind_value_from(
            ctx.worker, "progress"
        ).bind_visibility_from(ctx.worker, "is_running")


def main() -> None:
    parser = argparse.ArgumentParser(description="ACE-Step向けのメタデータを書き出すwebuiです")
    parser.add_argument("--host", default="127.0.0.1", help="default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=7869, help="default: 7869")
    parser.add_argument("--native", action="store_true", help="ブラウザでなくネイティブウィンドウで開く")
    parser.add_argument("--auto-reload", default=False, action="store_true", help="ソースコードが編集されたら自動でリロードする")

    args = parser.parse_args()
    # music_ctx = MusicCtx()
    # main_page(music_ctx)
    # music_ctx.worker._create_queue()
    ui.run(
        host=args.host,
        port=args.port,
        title="dataset-ui-music",
        reload=args.auto_reload,
        native=args.native,
    )


# if __name__ == "__main__":
if __name__ in {"__main__", "__mp_main__"}:
    main()
