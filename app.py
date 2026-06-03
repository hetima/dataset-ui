import sys
# 先に--develop-modeだけ調べる
_develop_mode = "--develop-mode" in sys.argv
_auto_reload_flag = False
import common.runtime_flags as runtime_flags
runtime_flags.develop_mode = _develop_mode

import argparse
from nicegui import ui, app
from common.model_cache import model_cache
from common.setting import cnfg
from music.index import main_page as page_music
from voice.index import main_page as page_voice
from edit.index import main_page as page_edit
from testpage.index import main_page as page_testpage


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
        '<a href="/">dataset-ui</a> / <a href="/voice">voice</a> | <a href="/music">music</a> | <a href="/edit">audio-edit</a> | '
    ).style("color: #646464")
    if _auto_reload_flag:
        ui.label(
            "※ --auto-reload フラグが有効になっています。ソースコードを編集すると自動でリロードされます。"
        ).style("color: #cc2222")


def footer():
    ui.html(
        '<a href="/">dataset-ui</a> ・ <a href="https://github.com/hetima/dataset-ui">GitHub</a>'
    ).classes("text-center w-full").style("color:#999999; font-size: 1em;")


def model_cache_sticky():
    """右上にモデルキャッシュ状態ボタンを表示する。"""

    @ui.refreshable
    def cache_card():
        entries = model_cache.entries
        if not entries:
            return
        with ui.page_sticky(position="top-right", x_offset=16, y_offset=16):
            with ui.card().classes("gap-0 q-pa-none").style("min-width: 200px; padding:0;"):
                with ui.expansion("モデルキャッシュ", value=True).classes("w-full").style("margin:0; padding:0;"):
                    for e in entries:
                        with ui.row().classes("items-center gap-1 q-px-sm"):
                            ui.icon("check_circle").style("color: teal; font-size: 1em")
                            ui.label(e.name).classes("text-sm")
                    ui.button("キャッシュをクリア", icon="delete", on_click=on_clear).props('color=red flat dense').classes("q-mt-xs")

    def on_clear():
        model_cache.dispose_all()

    client = ui.context.client
    def on_change():
        with client:
            cache_card.refresh()

    model_cache.add_change_listener(on_change)
    client.on_disconnect(lambda: model_cache.remove_change_listener(on_change))

    cache_card()


def efit_file_footer():
    """エディットページへの遷移フッタ"""
    with ui.footer(bordered=True).bind_visibility_from(cnfg, "has_edit_files").style(
        "background-color: #f5f5f5"
    ):
        with ui.row().classes("items-center gap-4"):
            ui.label().bind_text_from(cnfg, "edit_file_paths", lambda v: f"エディットプールに {len(v)} 件あります").style("color: #222")
            ui.button("エディットプールを開く", on_click=lambda: ui.navigate.to("/edit", new_tab=True)).props('flat dense')
            ui.button("クリアする", on_click=cnfg.clear_edit_file_paths).props('flat dense').style("color: #999")


@ui.page("/", title="dataset-ui")
def main_page():
    header()
    ui.markdown("""# dataset-ui
音声データセットに様々な処理を施すWeb UIです。

### 説明書
各ページの設定タブで書き出しフォルダとモデルフォルダとトレーニングフォルダは必ず確認することをお勧めします。初期設定ではレポジトリの中に作成されます。この3つの設定はすべてのページで共有されます。

自動保存されない操作が多いので保存ボタンを押し忘れないように注意してください。

モデルを選択するコンボボックスでは、リポジトリ形式のモデルID（user/model）を指定すると huggingface からダウンロードします（デフォルトのキャッシュにダウンロードされ再利用されます）。「ダウンロード」を押すとモデルフォルダにダウンロードされます。
        """).classes("items-start w-180")
    with ui.column().classes("items-start gap-0"):

        ui.link("voice", "/voice").style(
            'text-decoration: none; font-size: 3em; margin-top:16px;'
        )
        ui.label("音声データを編集")
        ui.label("音声の分割や書き起こしなどができます")

        ui.link("music", "/music").style(
            "text-decoration: none; font-size: 3em; margin-top:16px;"
        )
        ui.label("主に ACE-Step 向けのメタデータを編集")
        ui.label("楽曲のBPM、キーなどを解析します。歌詞の解析、編集などもできます")

        ui.link("audio-edit", "/edit").style(
            "text-decoration: none; font-size: 3em; margin-top:16px;"
        )
        ui.label("書き出した音声データを編集")
        ui.label("")
    if runtime_flags.develop_mode:
        ui.link("test", "/test").style("text-decoration: none; font-size: 1.8em;")

    footer()


@ui.page("/music", title="music - dataset-ui")
def main_page_music():
    header()
    page_music()
    footer()
    model_cache_sticky()
    efit_file_footer()


@ui.page("/voice", title="voice - dataset-ui")
def main_page_voice():
    header()
    page_voice()
    footer()
    model_cache_sticky()
    efit_file_footer()


@ui.page("/edit", title="audio-edit - dataset-ui")
def main_page_edit():
    header()
    page_edit()
    footer()
    model_cache_sticky()


@ui.page("/test", title="test - dataset-ui")
def test_page():
    header()
    page_testpage()
    footer()
    model_cache_sticky()
    efit_file_footer()


def make_startup_message(host: str, port: int):
    async def startup_message():
        print(f"dataset-ui ready  http://{host}:{port}", flush=True)
    return startup_message

def main() -> None:
    global _auto_reload_flag
    parser = argparse.ArgumentParser(description="音声データを解析・編集するwebuiです")
    parser.add_argument("--host", default="127.0.0.1", help="default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=7869, help="default: 7869")
    parser.add_argument("--native", action="store_true", help="ブラウザでなくネイティブウィンドウで開く")
    parser.add_argument("--auto-reload", default=False, action="store_true", help="ソースコードが編集されたら自動でリロードする")
    parser.add_argument("--develop-mode", default=False, action="store_true", help="開発者モード")
    args = parser.parse_args()
    _auto_reload_flag = args.auto_reload
    if args.develop_mode:
        _auto_reload_flag = True

    app.on_startup(make_startup_message(args.host, args.port))
    ui.run(
        host=args.host,
        port=args.port,
        title="dataset-ui",
        reload=_auto_reload_flag,
        native=args.native,
        show_welcome_message=False,
    )


# if __name__ == "__main__":
if __name__ in {"__main__", "__mp_main__"}:
    main()
