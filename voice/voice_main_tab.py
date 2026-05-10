import asyncio
from pathlib import Path
from typing import cast
from functools import partial

from nicegui import ui
from common.folder_picker import FolderPicker
from common.download_repo import download_repo_main
from common.setting import cnfg
from voice.qwen3_asr_transcriptor import transcript_main, asr_models
from voice.voice_app_ctx import VoiceCtx

def tab_main(ctx: VoiceCtx):

    def asr_download_finished(result) -> None:
        reload_asr_model()

    async def asr_download(repo_id: str) -> None:
        data = {"repo_id": repo_id, "output_dir": cnfg.models_dir / "qwen_asr"}
        await ctx.worker.run(download_repo_main, data, asr_download_finished)

    def transcript_finished(result) -> None:
        ctx.transcripted(result)

    async def transcript() -> None:
        if not cnfg.voice.asr_model:
            ui.notify("モデルを選択してください")
            return
        model_path = cnfg.models_dir / "qwen_asr" / cnfg.voice.asr_model
        if not model_path.exists():
            if cnfg.voice.asr_model.find("/") < 1:
                ui.notify(
                    f"モデルパス「  {str(cnfg.models_dir / "qwen_asr")}」 に「{cnfg.voice.asr_model}」フォルダが存在しません。"
                )
                return
            model_path_str = cnfg.music.acestep_transcriber_model
        else:
            model_path_str = str(model_path)
        files = ctx.target_files()
        data = {"model_path": model_path_str, "files": []}
        for music_file in files: # type: ignore
            data["files"].append(music_file["path"])
        if len(data["files"]) == 0:
            ui.notify("処理対象がありません")
            return
        await ctx.worker.run(transcript_main, data, transcript_finished)

    # def handle_cell_value_change(e):
    #     new_row = e.args["data"]
    #     ctx.file_grid.options["rowData"][:] = [
    #         row | new_row if row["name"] == new_row["name"] else row
    #         for row in ctx.file_grid.options["rowData"]
    #     ]

    async def pick_folder(path: str) -> None:
        result = await FolderPicker(path, read_all=False)
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
                value = cnfg.voice.last_dataset_path,
                label="dataset path",
                placeholder="フォルダのパスを入力...",
                on_change=lambda e: setattr(e.sender, "value", e.value),
            )
            .props('style="min-width: 500px" outlined clearable').classes("w-140")
        )
        ui.button("読み込み", on_click=lambda: ctx.load_files(path_input.value))

    def update_dataset_dropdown():
        dataset_dropdown.clear()
        with dataset_dropdown:
            for path in cnfg.voice.dataset_dirs:
                ui.item(path, on_click=partial(pick_folder, path)).classes("padd8")

    update_dataset_dropdown()
    ctx.dataset_dirs_refresh_func.append(update_dataset_dropdown)

    # ═══════════════════════════════════════════════════════════════════════════════
    # Audio analysis
    # ═══════════════════════════════════════════════════════════════════════════════

    with ui.row().classes("items-center gap-4"):
        ui.label("処理対象:")
        ui.toggle({"all": 'すべてのファイル', "selected": 'チェックした項目のみ'}).bind_value(ctx, 'target')
        ui.space()

    with ui.expansion("音声認識", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        ui.label("処理対象ファイルを Qwen3-ASR で音声認識します。")
        ui.label(
            "モデルフォルダの中にある Qwen3-ASR のフォルダ名を入力してください。"
            "リポジトリ形式のモデルID（user/model）を指定すると huggingface からダウンロードします"
            "（デフォルトのキャッシュにダウンロードされ再利用されます）。"
            "「ダウンロード」を押すとモデルフォルダにダウンロードされます。"
        ).classes("infotxt")
        with ui.row().classes("items-center gap-4"):
            opt = asr_models()
            val = cnfg.voice.asr_model
            if not val in opt:
                val = opt[0] if len(opt) > 0 else ""
            qwen_model_input = (
                ui.input(
                    label="transcriber model",
                    placeholder="モデルを選択、または入力",
                    on_change=lambda e: setattr(e.sender, "value", e.value),
                )
                .props('style="min-width: 300px" outlined')
                .bind_value(cnfg.voice, "asr_model")
            )
            with qwen_model_input.add_slot('append'):
                with ui.button(icon="arrow_drop_down").props('flat').classes("padd4"):
                    qwen_models_menu = ui.menu()

            ui.button("解析する", on_click=transcript).bind_enabled_from(ctx.worker, "can_run")

    def reload_asr_model():
        def hf_menu_item(models: list, repo_id: str):
            rid = repo_id.split("/")[-1]
            if rid not in models:
                with ui.item(
                    on_click=lambda: [
                        setattr(qwen_model_input, "value", repo_id),
                        qwen_models_menu.close(),
                    ]
                ).classes("padd8 items-center"):
                    ui.item_section(repo_id)
                    ui.button(
                        "ダウンロード",
                        on_click=lambda: [
                            qwen_models_menu.close(),
                            asyncio.ensure_future(asr_download(repo_id)),
                        ],
                    ).props("flat dense color=primary").style("margin-left: 8px").on(
                        "click", js_handler="(e) => e.stopPropagation()"
                    )
            else:
                ui.menu_item(
                    repo_id,
                    lambda: setattr(qwen_model_input, "value", repo_id),
                ).classes("padd8")
        models = asr_models()
        qwen_models_menu.clear()
        local_added = False
        with qwen_models_menu:
            for model in models:
                ui.menu_item(model, lambda m=model: setattr(qwen_model_input, "value", m)).classes("padd8")
                local_added = True
            if local_added:
                ui.separator()
            ui.menu_item("from huggingface").classes("padd8").enabled=False
            hf_menu_item(models, "Qwen/Qwen3-ASR-1.7B")
            hf_menu_item(models, "Qwen/Qwen3-ASR-0.6B")
            ui.separator()
            ui.menu_item("メニューを更新", lambda: reload_asr_model()).classes("padd8")

    reload_asr_model()
    ctx.model_refresh_func.append(reload_asr_model)

    # ═══════════════════════════════════════════════════════════════════════════════
    # ファイル一覧
    # ═══════════════════════════════════════════════════════════════════════════════

    with ui.row().classes("items-center gap-4"):
        player = ui.audio("")
        play_info = ui.label("")
    def play_src(path: str):
        player.set_source(path)
        player.play()
        play_info.set_text(Path(path).name)

    ctx.table = ui.table(
        columns=[
            {"label": "", "field": "path", "name": "play", "style": "width: 50px"},
            {
                "label": "Name",
                "field": "name",
                "name": "name",
                "align": "left",
            },
            {
                "name": "transcript",
                "field": "transcript",
                "label": "Transcript",
                "style": "white-space: nowrap; overflow: hidden;text-overflow: ellipsis; min-width:100px;",
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
            ).style('padding: 4px 8px;')

    # ═══════════════════════════════════════════════════════════════════════════════
    # Save files
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion('保存', value=True).classes('rounded-borders brdr overflow-hidden w-full').props('header-class="bg-grey-2 text-black"'):
        ui.label("メタデータをファイルに書き出します")
        with ui.row().classes("items-center gap-4"):
            ui.label("保存対象:")
            # ui.checkbox(".json").bind_value(ctx, "save_json")
            ui.checkbox(".txt").bind_value(ctx, "save_txt")
            ui.space()
            ui.button("保存", on_click=lambda: ctx.save_metadata())
