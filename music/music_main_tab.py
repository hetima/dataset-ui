import sys
from pathlib import Path
from typing import cast
from functools import partial

from nicegui import ui
from common.folder_picker import FolderPicker
from common.setting import cnfg
from common.xterm_dialog import XtermDialog
from music.music_app_ctx import MusicCtx
from common.wavesurfer import simple_player

LANGUAGE_LIST = ["ja", "en", "zh", "ko"]


def tab_main(ctx: MusicCtx):

    def acestep_transcriber_download_finished(success: bool) -> None:
        reload_acestep_transcriber_model()

    def acestep_transcriber_download(repo_id: str) -> None:
        cli = str(Path(__file__).parent.parent / "common" / "cli_task_download_repo.py")
        dlg = XtermDialog(
            args=[sys.executable, cli],
            title="ダウンロード",
            input_json={
                "repo_id": repo_id,
                "output_dir": str(cnfg.models_dir / "acestep_transcriber"),
            },
            finish_callback=acestep_transcriber_download_finished,
        )
        dlg.open()

    def progress_analyzed(part: dict) -> None:
        ctx.analyzed([part["data"]])

    def analyze() -> None:
        files = ctx.target_files()
        paths = [music_file["path"] for music_file in files]  # type: ignore
        if len(paths) == 0:
            ui.notify("処理対象がありません")
            return
        cnfg.save()
        cli = str(Path(__file__).parent / "cli_task_musicanalyze.py")
        dlg = XtermDialog(
            args=[sys.executable, cli],
            title="曲を解析する",
            input_json=paths,
            part_callback=progress_analyzed,
        )
        dlg.open()

    def progress_transcripted(part: dict) -> None:
        ctx.transcripted([part["data"]])

    def transcript() -> None:
        if not cnfg.music.acestep_transcriber_model:
            ui.notify("モデルを選択してください")
            return
        model_path = cnfg.models_dir / "acestep_transcriber" / cnfg.music.acestep_transcriber_model
        if not model_path.exists():
            if cnfg.music.acestep_transcriber_model.find("/") < 1:
                ui.notify(
                    f"モデルパス「  {str(cnfg.models_dir / 'acestep_transcriber')}」 に「{cnfg.music.acestep_transcriber_model}」フォルダが存在しません。"
                )
                return
            model_path_str = cnfg.music.acestep_transcriber_model
        else:
            model_path_str = str(model_path)
        files = ctx.target_files()
        paths = [f["path"] for f in files]  # type: ignore
        if not paths:
            ui.notify("処理対象がありません")
            return
        cnfg.save()
        cli = str(Path(__file__).parent / "cli_task_acestep_transcriptor.py")
        dlg = XtermDialog(
            args=[sys.executable, cli],
            title="歌詞を解析する",
            input_json={"model_path": model_path_str, "files": paths},
            part_callback=progress_transcripted,
        )
        dlg.open()

    # def handle_cell_value_change(e):
    #     new_row = e.args["data"]
    #     ctx.file_grid.options["rowData"][:] = [
    #         row | new_row if row["name"] == new_row["name"] else row
    #         for row in ctx.file_grid.options["rowData"]
    #     ]

    async def pick_folder(path: str) -> None:
        result = await FolderPicker(
            path, show_files_count=[".flac", ".ogg", ".mp3", ".wav", ".m4a"]
        )
        if isinstance(result, list) and len(result) > 0:
            path_input.value = result[0]
            ctx.load_files(path_input.value)

    # ═══════════════════════════════════════════════════════════════════════════════
    # Load files
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.row().classes("items-center gap-2"):
        dataset_dropdown = (
            ui.dropdown_button(icon="folder", auto_close=True)
            .props("outline")
            .style("padding: 4px 8px;")
        )
        path_input = (
            ui.input(
                value=cnfg.music.last_dataset_path,
                label="dataset path",
                placeholder="フォルダのパスを入力...",
                on_change=lambda e: setattr(e.sender, "value", e.value),
            )
            .props('style="min-width: 500px" outlined clearable')
            .classes("w-140")
        )
        ui.button("読み込み", on_click=lambda: ctx.load_files(path_input.value))

    def update_dataset_dropdown():
        dataset_dropdown.clear()
        with dataset_dropdown:
            for path in cnfg.music.dataset_dirs:
                ui.item(path, on_click=partial(pick_folder, path)).classes("padd8")

    update_dataset_dropdown()
    ctx.dataset_dirs_refresh_func.append(update_dataset_dropdown)

    # ═══════════════════════════════════════════════════════════════════════════════
    # Save files
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("保存", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):

        with ui.row().classes("items-center gap-4"):
            ui.label("処理対象:")
            ui.toggle(
                {"all": "すべてのファイル", "selected": "チェックした項目のみ"}
            ).bind_value(ctx, "target")

        ui.label("保存を押すと処理結果を書き出します。自動保存はされません")
        with ui.row().classes("items-center gap-4"):
            ui.label("保存対象:")
            ui.checkbox(".json").bind_value(ctx, "save_json")
            ui.checkbox(".lyrics.txt").bind_value(ctx, "save_lyrics")
            ui.checkbox(".txt (for AI Toolkit)").bind_value(ctx, "save_aitk")
            ui.button("保存", on_click=lambda: ctx.save_metadata())

    # ═══════════════════════════════════════════════════════════════════════════════
    # Audio analysis
    # ═══════════════════════════════════════════════════════════════════════════════

    def acestep_transcriber_models() -> list[str]:
        models_dir = cnfg.models_dir / "acestep_transcriber"
        if not models_dir.exists():
            return []
        return [
            p.name
            for p in models_dir.iterdir()
            if p.is_dir()
            # and "acestep" in p.name.lower()
            # and "transcriber" in p.name.lower()
        ]

    with ui.expansion('解析', value=False).classes('rounded-borders brdr overflow-hidden w-full').props('header-class="bg-grey-2 text-black"'):
        ui.label("処理対象ファイルを librosa で解析し、BPM、キー、拍子、時間を取得します")
        ui.button("曲を解析する", on_click=analyze)

    with ui.expansion("歌詞", value=False).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        ui.label("処理対象ファイルを ACE-Step Transcriber で解析し、歌詞を取得します。かなり時間がかかります。")
        ui.label(
            "モデルフォルダの中にある acestep_transcriber のフォルダ名を入力してください。"
            "リポジトリ形式のモデルID（user/model）を指定すると huggingface からダウンロードします"
            "（デフォルトのキャッシュにダウンロードされ再利用されます）。"
            "「ダウンロード」を押すとモデルフォルダにダウンロードされます。"
            "標準の acestep_transcriber は大量のメモリを必要とするので、動かない場合は 4-bit バージョンをお試しください"
        ).classes("infotxt")
        with ui.row().classes("items-center gap-4"):
            opt = acestep_transcriber_models()
            val = cnfg.music.acestep_transcriber_model
            if not val in opt:
                val = opt[0] if len(opt) > 0 else ""
            ace_model_input = ui.input(
                label="transcriber model",
                placeholder="モデルを選択、または入力",
                on_change=lambda e: setattr(e.sender, "value", e.value),
            ).props('style="min-width: 300px" outlined').bind_value(cnfg.music, "acestep_transcriber_model")
            with ace_model_input.add_slot('append'):
                with ui.button(icon="arrow_drop_down").props('flat').classes("padd4"):
                    ace_models_menu = ui.menu()

            ui.button("歌詞を解析する", on_click=transcript)

    def reload_acestep_transcriber_model():
        def hf_menu_item(models:list, repo_id:str):
            rid = repo_id.split("/")[-1]
            if rid not in models:
                with ui.item(
                    on_click=lambda: [
                        setattr(ace_model_input, "value", repo_id),
                        ace_models_menu.close(),
                    ]
                ).classes("padd8 items-center"):
                    ui.item_section(repo_id)
                    ui.button(
                        "ダウンロード",
                        on_click=lambda: acestep_transcriber_download(repo_id),
                    ).props("flat dense color=primary").style("margin-left: 8px").on(
                        "click", js_handler="(e) => e.stopPropagation()"
                    )
            else:
                ui.menu_item(
                    repo_id,
                    lambda: setattr(ace_model_input, "value", repo_id),
                ).classes("padd8")
        models = acestep_transcriber_models()
        ace_models_menu.clear()
        local_added = False
        with ace_models_menu:
            for model in models:
                ui.menu_item(model, lambda m=model: setattr(ace_model_input, "value", m)).classes("padd8")
                local_added = True
            if local_added:
                ui.separator()
            ui.menu_item("from huggingface").classes("padd8").enabled=False
            # ACE-Step/acestep-transcriber
            hf_menu_item(models, "ACE-Step/acestep-transcriber")
            hf_menu_item(models, "hrktxz/acestep-transcriber-4bit")
            ui.separator()
            ui.menu_item("メニューを更新", lambda: reload_acestep_transcriber_model()).classes("padd8")

    reload_acestep_transcriber_model()
    ctx.model_refresh_func.append(reload_acestep_transcriber_model)

    with ui.expansion('手動変更', value=False).classes('rounded-borders brdr overflow-hidden w-full').props('header-class="bg-grey-2 text-black"'):
        ui.label("処理対象ファイルのメタデータを手動で変更します")
        with ui.row().classes("items-center gap-4"):
            lang = ui.select(options=LANGUAGE_LIST, with_input=True, new_value_mode="add", label="language").classes('w-30').props("outlined")
            ui.button("languageを設定", on_click=lambda e: ctx.set_lang(cast(str, lang.value)))
            ui.space()
            capt = ui.input(placeholder="captionを入力", label="caption").classes('w-100').props("outlined")
            ui.button("captionを設定", on_click=lambda e: ctx.set_caption(cast(str, capt.value)))

    # ═══════════════════════════════════════════════════════════════════════════════
    # ファイル一覧
    # ═══════════════════════════════════════════════════════════════════════════════

    # with ui.row().classes("items-center gap-4"):
    #     player = ui.audio("")
    #     play_info = ui.label("")
    # def play_src(path: str):
    #     player.set_source(path)
    #     player.play()
    #     play_info.set_text(Path(path).name)
    ws = simple_player("ws_01", visible=False, autoplay=True)
    def play_src(path: str):
        ws.container.set_visibility(True)
        ws.ws.load(path)

    ctx.table = ui.table(
        columns=[
            {"label": "", "field": "path", "name": "expand", "style": "width: 30px"},
            {"label": "", "field": "path", "name": "play", "style": "width: 30px"},
            {
                "label": "Name",
                "field": "name",
                "name": "name",
                "align": "left",
            },
            {
                "name": "caption",
                "field": "caption",
                "label": "Caption",
                "style": "white-space: nowrap; overflow: hidden;text-overflow: ellipsis; min-width:100px; max-width:160px",
                "align": "left",
            },
            {
                "name": "lyrics",
                "field": "lyrics",
                "label": "Lyrics",
                "style": "white-space: nowrap; overflow: hidden;text-overflow: ellipsis; min-width:100px; max-width:160px",
                "align": "left",
            },
            {
                "label": "Lang",
                "field": "language",
                "editable": True,
                "style": "width: 80px",
                "name": "language",
                "align": "left",
            },
            {
                "label": "BPM",
                "field": "bpm",
                "editable": True,
                "name": "bpm",
                "style": "width: 80px",
                "align": "left",
            },
            {
                "label": "KEY",
                "field": "keyscale",
                "editable": True,
                "name": "keyscale",
                "style": "width: 80px",
                "align": "left",
            },
            {
                "label": "Timesig",
                "field": "timesignature",
                "editable": True,
                "name": "timesignature",
                "style": "width: 80px",
                "align": "left",
            },
            {
                "label": "Duration",
                "field": "duration",
                "editable": True,
                "name": "duration",
                "style": "width: 80px",
                "align": "left",
            },
        ],
        rows=[],
        selection="multiple",
        row_key="name",
    ).classes("h-120 w-full no-shadow brdr q-pa-none")
    with ctx.table.add_slot('body-cell-play'):
        with ctx.table.cell('play'):
            ui.button(icon="play_circle").props('flat').on(
                'click',
                js_handler='() => emit(props.value)',
                handler=lambda e: play_src(e.args),
            ).style('padding: 2px 4px;')
    with ctx.table.add_slot("body-cell-expand"):
        with ctx.table.cell("expand"):
            ui.button().props(
                "flat"
                " :icon=\"props.expand ? 'expand_less' : 'expand_more'\""
                " :style=\"props.row.is_expandable ? 'padding: 2px 4px' : 'padding: 2px 4px; display: none'\""
            ).on(
                "click",
                js_handler="() => { props.expand = !props.expand; emit({ value: props.value, expand: props.expand }) }",
                handler=lambda e: print(e.args),
            )
