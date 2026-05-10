import argparse
from nicegui import ui, app
from common.worker import Worker
from music.index import main_page as page_music
from voice.index import main_page as page_voice

_worker: Worker = Worker()
_auto_reload_flag = False

def header():
    ui.query('body').style('font-family: Roboto, "BIZ UDPGothic", "BIZ UDPゴシック", sans-serif;')
    ui.add_css("""
h1 {
    font-size: 3.4em;
    margin: 0.2em 0 0.2em 0;
}
h2 {
    font-size: 2em;
    margin: 0.2em 0 0.2em 0;
}
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

.dialog-xterm .terminal {
    padding: 6px 22px 6px 6px;
}

""")
    ui.colors(secondary='#747474')
    if _auto_reload_flag:
        ui.label(
            "※ --auto-reload フラグが有効になっています。ソースコードを編集すると自動でリロードされます。"
        ).style("color: #cc2222")


def footer():
    ui.html(
        '<a href="/">dataset-ui</a> ・ <a href="https://github.com/hetima/dataset-ui">GitHub</a>'
    ).classes("text-center w-full").style("color:#999999; font-size: 1em;")

    # ═══════════════════════════════════════════════════════════════════════════════
    # 処理中UI
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.footer(bordered=True).bind_visibility_from(_worker, "is_running").style(
        "background-color: #f2f2f2"
    ):
        with ui.row().classes("items-center gap-4"):
            ui.spinner(size='lg')
            with ui.column():
                with ui.row().classes("items-center gap-4"):
                    ui.label("バックグラウンド処理を実行しています").style('color: #010101')
                    ui.label("").style("color: #010101").bind_text_from(
                        _worker, "elapsed_time"
                    )
                with ui.row().classes("items-center gap-4"):
                    ui.button(
                        "処理を強制終了する",
                        icon="warning",
                        on_click=_worker.terminate_now,
                    ).bind_visibility_from(_worker, "is_running").props(
                        'color="red"'
                    ).tooltip(
                        "強制的に子プロセスを終了"
                    )
                    ui.label().style("color: #010101").bind_text_from(_worker, "status")
        ui.linear_progress(show_value=False).props("instant-feedback").bind_value_from(
            _worker, "progress"
        ).bind_visibility_from(_worker, "is_running")


@ui.page("/", title="dataset-ui")
def main_page():
    header()
    ui.markdown("""## dataset-ui""")
    ui.link("music", "/music").style('text-decoration: none; font-size: 3em;')
    ui.label("ACE-Step 向けのメタデータを編集")
    ui.link("voice", "/voice").style('text-decoration: none; font-size: 3em;')
    ui.label("音声データを編集")
    footer()


@ui.page("/music", title="dataset-ui-music")
def main_page_music():
    header()
    page_music(_worker)
    footer()

@ui.page("/voice", title="dataset-ui-voice")
def main_page_voice():
    header()
    page_voice(_worker)
    footer()


@ui.page("/test", title="dataset-ui")
def test_page():
    header()
    ui.label("test")
    footer()


def make_startup_message(host: str, port: int):
    async def startup_message():
        print(f"dataset-ui ready  http://{host}:{port}", flush=True)
    return startup_message

def main() -> None:
    global _auto_reload_flag
    parser = argparse.ArgumentParser(description="ACE-Step向けのメタデータを書き出すwebuiです")
    parser.add_argument("--host", default="127.0.0.1", help="default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=7869, help="default: 7869")
    parser.add_argument("--native", action="store_true", help="ブラウザでなくネイティブウィンドウで開く")
    parser.add_argument("--auto-reload", default=False, action="store_true", help="ソースコードが編集されたら自動でリロードする")

    args = parser.parse_args()
    _auto_reload_flag = args.auto_reload
    app.on_startup(make_startup_message(args.host, args.port))
    ui.run(
        host=args.host,
        port=args.port,
        title="dataset-ui",
        reload=args.auto_reload,
        native=args.native,
        show_welcome_message=False,
    )


# if __name__ == "__main__":
if __name__ in {"__main__", "__mp_main__"}:
    main()
