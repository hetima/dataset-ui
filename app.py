import argparse
from nicegui import ui, app
from common.worker import Worker
from music.index import main_page as page_music
from voice.index import main_page as page_voice
from testpage.index import main_page as page_testpage

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
h3 {
    font-size: 1.6em;
    margin: 0.2em 0 0.2em 0;
}
h4 {
    font-size: 1.3em;
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
    ui.html(
        '<a href="/">dataset-ui</a> / <a href="/music">music</a> | <a href="/voice">voice</a>'
    ).style("color: #646464")
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
    ui.markdown("""# dataset-ui
音声データセットに様々な処理を施すWeb UIです。

### 説明書
各ページの設定タブで書き出しフォルダとモデルフォルダは必ず確認することをお勧めします。初期設定ではレポジトリの中に作成されます。この2つの設定はすべてのページで共有されます。

自動保存されない操作が多いので保存ボタンを押し忘れないように注意してください。

モデルを選択するコンボボックスでは、リポジトリ形式のモデルID（user/model）を指定すると huggingface からダウンロードします（デフォルトのキャッシュにダウンロードされ再利用されます）。「ダウンロード」を押すとモデルフォルダにダウンロードされます。
        """).classes("items-start w-180")
    with ui.column().classes("items-start gap-0"):
        ui.link("music", "/music").style(
            "text-decoration: none; font-size: 3em; margin-top:16px;"
        )
        ui.label("主に ACE-Step 向けのメタデータを編集")
        ui.label("楽曲のBPM、キーなどを解析します。歌詞の解析、編集などもできます")
        ui.link("voice", "/voice").style(
            'text-decoration: none; font-size: 3em; margin-top:16px;'
        )
        ui.label("音声データを編集")
        ui.label("音声の分割や書き起こしなどができます")
    if _auto_reload_flag:
        ui.link("test", "/test").style("text-decoration: none; font-size: 1.8em;")

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
    page_testpage(_worker)
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
