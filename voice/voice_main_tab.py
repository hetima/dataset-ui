import asyncio
from pathlib import Path
from typing import cast
from functools import partial

from nicegui import ui
from common.folder_picker import FolderPicker
from common.download_repo import download_repo_main
from common.setting import cnfg
from common.message_dialog import show_confirm_dialog
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
        """処理対象のファイルを Qwen3-ASR で音声認識するタスクを実行"""
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
        if len(files) == 0:
            ui.notify("処理対象がありません")
            return
        data = {"model_path": model_path_str, "files": []}
        for music_file in files: # type: ignore
            data["files"].append(music_file["path"])
        await ctx.worker.run(transcript_main, data, transcript_finished)

    async def confirm_dir_exists(files: list) -> bool:
        exists_dirs = []
        for f in files:
            path = Path(f["path"])
            output_dir = path.stem
            dst = path.parent / output_dir
            if dst.exists():
                exists_dirs.append(dst)
        if len(exists_dirs) > 0:
            msg = "分割ファイルの出力先が存在しています。<br><br>"
            for d in exists_dirs:
                msg += f"- {str(d)}<br>"
            confirm = await show_confirm_dialog(
                msg + "<br>これらのフォルダを削除して処理を続行しますか？"
            )
            return confirm
        return True

    def segment_finished(result) -> None:
        ctx.segment_finished(result)

    async def segment_silence(
        min_sec=2, max_sec=5, silence_thresh: int = -60, output_format: str = "wav"
    ) -> None:
        """無音区間で分割して保存するタスクを実行
        Args: min_sec: チャンクの最小長さ(秒)
              max_sec: チャンクの最大長さ(秒)
              output_format: 出力フォーマット ("wav", "mp3", "flac" のいずれか)
              silence_thresh: 無音とみなす音量の閾値 (dB)
        """
        from voice.segment_silence import segment_silence_main

        min_sec = float(min_sec)
        max_sec = float(max_sec)

        files = ctx.target_files()
        if len(files) == 0:
            ui.notify("処理対象がありません")
            return
        if not await confirm_dir_exists(files):
            return
        data = {
            "files": [f["path"] for f in files],
            "output_dir": None,
            "overwrite": True,
            "format": output_format,
            "min_sec": min_sec,
            "max_sec": max_sec,
            "silence_thresh": silence_thresh,
        }
        await ctx.worker.run(segment_silence_main, data, segment_finished)

    async def segment_equally(frame_count=5, fps=1, output_format: str = "wav") -> None:
        """均等に分割して保存するタスクを実行
        Args: frame_count: フレーム数
              fps: フレームレート。1にするとフレーム数=秒数になるので、秒数で分割したい場合は1を指定してください。
              output_format: 出力フォーマット ("wav", "mp3", "flac" のいずれか)
        """
        from voice.segment_equally import segment_equally_main

        segment_sec = float(frame_count) / float(fps)
        files = ctx.target_files()
        if len(files) == 0:
            ui.notify("処理対象がありません")
            return
        if not await confirm_dir_exists(files):
            return
        data = {
            "files": [f["path"] for f in files],
            "output_dir": None,
            "overwrite": True,
            "format": output_format,
            "segment_sec": segment_sec,
        }
        await ctx.worker.run(segment_equally_main, data, segment_finished)

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

    with ui.expansion("音声分割", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        with ui.splitter().classes("q-splitter--no-margin").props('separator-class="q-mx-md"') as segment_splitter:
            with segment_splitter.before:
                ui.label("処理対象ファイルを無音区間で分割します。")
                ui.label(
                    "分割したファイルは元のファイルと同じ階層にフォルダを作成し、「ファイル名/ファイル名_part001.wav」という名前で保存されます。"
                ).classes("infotxt")
                with ui.row().classes("items-center gap-4"):
                    input_min_sec = ui.input(label="最小秒数", placeholder="例: 2", value="2").props("outlined style='width: 100px;'")
                    input_max_sec = ui.input(label="最大秒数", placeholder="例: 5", value="5").props("outlined style='width: 100px;'")
                    input_thresh = ui.input(label="無音閾値(dB)", placeholder="例: -60", value="-60").props("outlined style='width: 100px;'")
                    input_format = ui.select(
                        label="出力",
                        options={"wav": "wav", "mp3": "mp3", "flac": "flac"},
                        value="wav",
                    ).props("outlined style='width: 120px;'")
                    ui.button("分割する").bind_enabled_from(ctx.worker, "can_run").on_click(
                        lambda: segment_silence(
                            min_sec=input_min_sec.value,  # type: ignore
                            max_sec=input_max_sec.value,  # type: ignore
                            silence_thresh=input_thresh.value,  # type: ignore
                            output_format=input_format.value,
                        )
                    )
            with segment_splitter.after:
                ui.label("処理対象ファイルを均等に分割します。")
                ui.label(
                    "分割したファイルは元のファイルと同じ階層にフォルダを作成し、「ファイル名/ファイル名_part001.wav」という名前で保存されます。"
                ).classes("infotxt")
                ui.label("フレーム数とfpsから秒数を計算して分割します。fpsを1にするとフレーム数=秒数になるので、秒数で分割したい場合はfpsを1にしてください。").classes("infotxt")

                with ui.row().classes("items-center gap-4"):
                    input_parts = ui.input(
                        label="フレーム数", placeholder="例: 5", value="5"
                    ).props("outlined style='width: 100px;'")
                    input_fps = ui.input(label="FPS", placeholder="例: 24", value="1").props("outlined style='width: 100px;'")
                    input_format2 = ui.select(
                        label="出力",
                        options={"wav": "wav", "mp3": "mp3", "flac": "flac"},
                        value="wav",
                    ).props("outlined style='width: 120px;'")
                    ui.button("分割する").bind_enabled_from(
                        ctx.worker, "can_run"
                    ).on_click(
                        lambda: segment_equally(
                            frame_count=input_parts.value,  # type: ignore
                            fps=input_fps.value,  # type: ignore
                            output_format=input_format2.value,
                        )
                    )

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
            {"label": "", "field": "path", "name": "expand", "style": "width: 30px"},
            {"label": "", "field": "path", "name": "play", "style": "width: 30px"},
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
            ).style('padding: 2px 4px;')
    with ctx.table.add_slot("body-cell-expand"):
        with ctx.table.cell("expand"):
            ui.button().props(
                'flat'
                ' :icon="props.expand ? \'expand_less\' : \'expand_more\'"'
                ' :style="props.row.is_expandable ? \'padding: 2px 4px\' : \'padding: 2px 4px; display: none\'"'
            ).on(
                "click",
                js_handler="() => { props.expand = !props.expand; emit({ value: props.value, expand: props.expand }) }",
                handler=lambda e: print(e.args),
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
