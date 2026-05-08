from pathlib import Path
from typing import cast
from functools import partial

from nicegui import ui
from common.folder_picker import FolderPicker
from common.download_repo import download_repo
from voice.voice_setting import cnfg
from voice.qwen3_asr_transcriptor import transcript_main, asr_models
from voice.voice_app_ctx import VoiceCtx

def tab_main(ctx: VoiceCtx):

    def transcript_finished(result) -> None:
        ctx.transcripted(result)

    async def transcript() -> None:
        if not cnfg.asr_model:
            ui.notify("モデルを選択してください")
            return
        model_path = cnfg.models_dir / cnfg.asr_model
        if not model_path.exists():
            if cnfg.asr_model.find("/") < 1:
                ui.notify(
                    f"モデルパス「  {str(cnfg.models_dir)}」 に「{cnfg.asr_model}」フォルダが存在しません。ダウンロードしてください"
                )
                return
        files = ctx.target_files()
        data = []
        for music_file in files: # type: ignore
            data.append(music_file["path"])
        if len(data) == 0:
            ui.notify("処理対象がありません")
            return
        cnfg.save()
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

    # ═══════════════════════════════════════════════════════════════════════════════
    # Load files
    # ═══════════════════════════════════════════════════════════════════════════════

    with ui.row().classes("items-center gap-2"):
        path_input = (
            ui.input(
                value = cnfg.last_dataset_path,
                label="dataset path",
                placeholder="フォルダのパスを入力...",
                on_change=lambda e: setattr(e.sender, "value", e.value),
            )
            .props('style="min-width: 500px" outlined clearable').classes("w-140")
        )
        dataset_dropdown = ui.dropdown_button(icon="folder", auto_close=True).props('outline')
        ui.button("読み込み", on_click=lambda: ctx.load_files(path_input.value))

    def update_dataset_dropdown():
        dataset_dropdown.clear()
        with dataset_dropdown:
            for path in cnfg.dataset_dirs:
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
        ui.label("処理対象ファイルを QWEN3-ASR で音声認識します。")
        ui.label("モデルフォルダの中にある QWEN3-ASR のフォルダ名を入力してください。"
                 "huggingface リポジトリ形式のモデルID（user/model）を指定すると huggingface からダウンロードします"
                 "（デフォルトのキャッシュにダウンロードされ再利用されます）。").classes('infotxt')
        with ui.row().classes("items-center gap-4"):
            opt = asr_models()
            val = cnfg.asr_model
            if not val in opt:
                val = opt[0] if len(opt) > 0 else ""
            ace_model_input = (
                ui.input(
                    label="transcriber model",
                    placeholder="モデルを選択、または入力",
                    on_change=lambda e: setattr(e.sender, "value", e.value),
                )
                .props('style="min-width: 300px" outlined')
                .bind_value(cnfg, "asr_model")
            )
            with ace_model_input.add_slot('append'):
                with ui.button(icon="arrow_drop_down").props('flat').classes("padd4"):
                    ace_models_menu = ui.menu()

            ui.button("解析する", on_click=transcript).bind_enabled_from(ctx.worker, "can_run")

    def download_model(model_id: str):
        download_repo(model_id, str(cnfg.models_dir))
        # TODO: 完了したらメニュー更新

    def reload_asr_model():
        models = asr_models()
        ace_models_menu.clear()
        local_added = False
        with ace_models_menu:
            for model in models:
                ui.menu_item(model, lambda m=model: setattr(ace_model_input, "value", m)).classes("padd8")
                local_added = True
            if local_added:
                ui.separator()
            ui.menu_item("from huggingface").classes("padd8").enabled=False
            # Qwen3-ASR-1.7B
            if "Qwen3-ASR-1.7B" not in models:
                with ui.item(on_click=lambda: [setattr(ace_model_input, "value", "Qwen/Qwen3-ASR-1.7B"), ace_models_menu.close()]).classes("padd8 items-center"):
                    ui.item_section("Qwen/Qwen3-ASR-1.7B")
                    ui.button(
                        "ダウンロードする",
                        on_click=lambda: [
                            ace_models_menu.close(),
                            download_model("Qwen/Qwen3-ASR-1.7B"),
                        ],
                    ).props("flat dense color=primary").style("margin-left: 8px").on(
                        "click", js_handler="(e) => e.stopPropagation()"
                    )
            else:
                ui.menu_item(
                    "Qwen/Qwen3-ASR-1.7B",
                    lambda: setattr(ace_model_input, "value", "Qwen/Qwen3-ASR-1.7B"),
                ).classes("padd8")
            # Qwen3-ASR-0.6B
            if "Qwen3-ASR-0.6B" not in models:
                with ui.item(on_click=lambda: [setattr(ace_model_input, "value", "Qwen/Qwen3-ASR-0.6B"), ace_models_menu.close()]).classes("padd8 items-center"):
                    ui.item_section("Qwen/Qwen3-ASR-0.6B")
                    ui.button(
                        "ダウンロードする",
                        on_click=lambda: [
                            ace_models_menu.close(),
                            download_model("Qwen/Qwen3-ASR-0.6B"),
                        ],
                    ).props("flat dense color=primary").style("margin-left: 8px").on(
                        "click", js_handler="(e) => e.stopPropagation()"
                    )
            else:
                ui.menu_item(
                    "Qwen/Qwen3-ASR-0.6B",
                    lambda: setattr(ace_model_input, "value", "Qwen/Qwen3-ASR-0.6B"),
                ).classes("padd8")
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
            {"label": "", "field": "path", "name": "play", "style": 'width: 50px'},
            {"label": "Name", "field": "name", "name": "name", "align": 'left',},
            {
                "name": "caption",
                "field": "caption",
                "label": "Caption",
                "style": 'white-space: nowrap; overflow: hidden;text-overflow: ellipsis; min-width:100px;',
                "align": 'left',
            },
        ],
        rows=[],
        selection="multiple",
        row_key='name',
    ).classes('h-120 w-full no-shadow brdr q-pa-none')
    with ctx.table.add_slot('body-cell-play'):
        with ctx.table.cell('play'):
            ui.button(icon="play_circle").props('flat').on(
                'click',
                js_handler='() => emit(props.value)',
                handler=lambda e: play_src(e.args),
            )

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
