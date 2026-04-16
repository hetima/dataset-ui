from pathlib import Path
from typing import cast

from nicegui import ui
from music.setting import cnfg
from music.musicanalyze import analyze_main
from music.acestep_transcriptor import transcript_main, acestep_transcriber_models
from music.app_ctx import MusicCtx

LANGUAGE_LIST = ["ja", "en", "zh", "ko"]


def tab_main(ctx: MusicCtx):

    def analyze_finished(result) -> None:
        ctx.analyzed(result)
        
    async def analyze() -> None:
        files = ctx.target_files()
        data = []
        for music_file in files: # type: ignore
            data.append(music_file["path"])
        if len(data) == 0:
            ui.notify("処理対象がありません")
            return
        cnfg.save()
        await ctx.worker.run(analyze_main, data, analyze_finished)
    
    def transcript_finished(result) -> None:
        ctx.transcripted(result)
        
    async def transcript() -> None:
        if not cnfg.acestep_transcriber_model:
            ui.notify("モデルを選択してください")
            return
        model_path = cnfg.models_dir / cnfg.acestep_transcriber_model
        if not model_path.exists():
            ui.notify(
                f"モデルパス「  {str(cnfg.models_dir)}」 に「{cnfg.acestep_transcriber_model}」フォルダが存在しません。ダウンロードしてください"
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
    

    # ═══════════════════════════════════════════════════════════════════════════════
    # Load files 
    # ═══════════════════════════════════════════════════════════════════════════════

    with ui.row().classes("items-center gap-2"):
        path_input = (
            ui.input(
                placeholder="フォルダのパスを入力...",
                on_change=lambda e: setattr(e.sender, "value", e.value),
            )
            .props('style="min-width: 500px"')
            .props("clearable")
        )
        ui.button("読み込み", on_click=lambda: ctx.load_files(path_input.value.strip()))

    # ═══════════════════════════════════════════════════════════════════════════════
    # Audio analysis
    # ═══════════════════════════════════════════════════════════════════════════════

    with ui.row().classes("items-center gap-4"):
        ui.label("処理対象:")
        ui.toggle({"all": 'すべてのファイル', "selected": 'チェックした項目のみ'}).bind_value(ctx, 'target')
        ui.space()
    
    with ui.expansion('解析', value=True).classes('rounded-borders brdr overflow-hidden w-full').props('header-class="bg-grey-2 text-black"'):
        ui.label("処理対象ファイルを librosa で解析し、BPM、キー、拍子、時間を取得します")
        ui.button("曲を解析する", on_click=analyze).bind_enabled_from(ctx.worker, "can_run")
    
    with ui.expansion('歌詞', value=True).classes('rounded-borders brdr overflow-hidden w-full').props('header-class="bg-grey-2 text-black"'):
        ui.label("処理対象ファイルを ACE-Step Transcriber で解析し、歌詞を取得します。かなり時間がかかります。")
        with ui.row().classes("items-center gap-4"):
            ui.label("モデル:")
            opt = acestep_transcriber_models()
            val = cnfg.acestep_transcriber_model
            if not val in opt:
                val = opt[0] if len(opt) > 0 else None
                cnfg.set_acestep_transcriber_model(val)
            ace_models = ui.select(options=opt,
                value = val,
                on_change=lambda e: cnfg.set_acestep_transcriber_model(e.value)).props('style="min-width: 120px"')
            with ui.button(icon="refresh", on_click=lambda: reload_acestep_transcriber_model()).props('flat'):
                ui.tooltip("モデル一覧を更新").props('delay=600')
            ui.button("歌詞を解析する", on_click=transcript).bind_enabled_from(ctx.worker, "can_run")
    
    def reload_acestep_transcriber_model():
        ace_models.set_options(acestep_transcriber_models())
    ctx.model_refresh_func.append(reload_acestep_transcriber_model)

    with ui.expansion('手動変更', value=False).classes('rounded-borders brdr overflow-hidden w-full').props('header-class="bg-grey-2 text-black"'):
        ui.label("処理対象ファイルのメタデータを手動で変更します")
        with ui.row().classes("items-center gap-4"):
            lang = ui.select(options=LANGUAGE_LIST, with_input=True, new_value_mode="add").classes('w-30')
            ui.button("languageを設定", on_click=lambda e: ctx.set_lang(cast(str, lang.value)))
            ui.space()
            capt = ui.input(placeholder="caption...",).classes('w-100')
            ui.button("captionを設定", on_click=lambda e: ctx.set_caption(cast(str, capt.value)))

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
                "style": 'white-space: nowrap; overflow: hidden;text-overflow: ellipsis; min-width:100px; max-width:160px',
                "align": 'left',
            },
            {
                "name": "lyrics",
                "field": "lyrics",
                "label": "Lyrics",
                "style": 'white-space: nowrap; overflow: hidden;text-overflow: ellipsis; min-width:100px; max-width:160px',
                "align": 'left',
            },
            {
                "label": "Lang",
                "field": "language",
                "editable": True,
                "style": 'width: 80px',
                "name": "language",
                "align": 'left',
            },
            {
                "label": "BPM",
                "field": "bpm",
                "editable": True,
                "name": "bpm",
                "style": 'width: 80px',
                "align": 'left',
            },
            {
                "label": "KEY",
                "field": "keyscale",
                "editable": True,
                "name": "keyscale",
                "style": 'width: 80px',
                "align": 'left',
            },
            {
                "label": "Timesig",
                "field": "timesignature",
                "editable": True,
                "name": "timesignature",
                "style": 'width: 80px',
                "align": 'left',
            },
            {
                "label": "Duration",
                "field": "duration",
                "editable": True,
                "name": "duration",
                "style": 'width: 80px',
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
            ui.checkbox(".json").bind_value(ctx, "save_json")
            ui.checkbox(".lyrics.txt").bind_value(ctx, "save_lyrics")
            ui.checkbox(".txt (for AI Toolkit)").bind_value(ctx, "save_aitk")
            ui.space()
            ui.button("保存", on_click=lambda: ctx.save_metadata())
            
