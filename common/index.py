from nicegui import ui
import common.runtime_flags as runtime_flags
from common.setting import cnfg


def main_page():
    ui.markdown("""# dataset-ui
音声データセットに様々な処理を施すWeb UIです。""")

    with ui.tabs().classes("w-full").classes("text-dark").props(
        'inline-label align="left"'
    ) as tabs:
        main_Tab = ui.tab("main", label="メイン", icon="apps")
        setting_tab = ui.tab("setting", label="設定", icon="settings")
    with ui.tab_panels(tabs, animated=False, value=main_Tab).classes("w-full"):
        with ui.tab_panel(main_Tab):
            tab_main()
        with ui.tab_panel(setting_tab):
            tab_setting()

def tab_main():
    ui.markdown("""
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

def tab_setting():
    def set_models_root(path: str | None):
        if path and cnfg.set_models_dir(path):
            ui.notify("モデルパスを保存しました")

    def set_outputs_dir(path: str | None):
        if path and cnfg.set_outputs_dir(path):
            ui.notify("書き出しパスを保存しました")

    def set_train_dir(path: str | None):
        if path and cnfg.set_train_dir(path):
            ui.notify("トレーニングパスパスを保存しました")

    # ═══════════════════════════════════════════════════════════════════════════════
    # 出力パス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("書き出しパス", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("成果物を書き出すフォルダパスを入力してください")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            outputs_path_input = ui.input(
                value=str(cnfg.outputs_dir),
                label="outputs path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button(
                "保存",
                on_click=lambda: set_outputs_dir(outputs_path_input.value),
            )

    # ═══════════════════════════════════════════════════════════════════════════════
    # モデルパス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("モデルパス", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("モデルをダウンロードするフォルダパスを入力してください")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            model_root_path_input = ui.input(
                value=str(cnfg.models_dir),
                label="models root path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button(
                "保存",
                on_click=lambda: set_models_root(model_root_path_input.value),
            )

    # ═══════════════════════════════════════════════════════════════════════════════
    # トレーニングパス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("トレーニングパス", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("トレーニングデータを配置するフォルダパスを入力してください")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            train_path_input = ui.input(
                value=str(cnfg.train_dir),
                label="train path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button(
                "保存",
                on_click=lambda: set_train_dir(train_path_input.value or ""),
            )

    # ═══════════════════════════════════════════════════════════════════════════════
    # HuggingFace Token
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("HuggingFace Token", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("ゲートモデルのダウンロードに必要な場合に設定してください。設定するとダウンロード処理に HF_TOKEN として渡されます")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            hf_token_input = ui.input(
                value=cnfg.hf_token,
                label="HuggingFace token",
                placeholder="hf_...",
                password=True,
                password_toggle_button=True,
            ).props('style="min-width: 400px" outlined dense')
            ui.button(
                "保存",
                on_click=lambda: [
                    setattr(cnfg, "hf_token", hf_token_input.value),
                    cnfg.save(),
                    ui.notify("HuggingFace Token を保存しました"),
                ],
            )
