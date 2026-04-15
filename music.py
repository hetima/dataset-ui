import argparse
from pathlib import Path
from typing import cast

from nicegui import app, binding, ui
from nicegui.elements.table import Table
from src.setting import cnfg
from src.musicfile import MusicFile
from src.worker import Worker
from src.musicanalyze import analyze_main
from src.acestep_transcriptor import transcript_main, acestep_transcriber_models

SUPPORTED_EXTENSIONS = [".wav", ".flac", ".ogg", ".mp3", ".m4a"]
LANGUAGE_LIST = ["ja", "en", "zh", "ko"]

@binding.bindable_dataclass
class MusicCtx:
    def __init__(self):
        self.name = "dataset-ui-music"
        self.files = []
        self.table: Table
        self.save_json: bool = True
        self.save_lyrics: bool = True
        self.save_aitk: bool = False
        self.worker: Worker = _worker
        self.target = "all"

    def load_files(self, path: str) -> None:
        folder_path = path
        if not folder_path:
            ui.notify("フォルダパスを入力してください", type="warning")
            return

        folder = Path(folder_path)
        if not folder.is_dir():
            ui.notify(f"フォルダが見つかりません: {folder_path}", type="negative")
            return

        self.files = []
        # for ext in SUPPORTED_EXTENSIONS:
        for file in sorted(folder.glob(f"*")):
            if not file.suffix in SUPPORTED_EXTENSIONS:
                continue

            musicfile = MusicFile.from_audio_file(file)
            self.files.append(musicfile.to_dict())

        if not self.files:
            ui.notify("サポート対象のファイルが見つかりません")
            return

        self.table.rows = self.files
        self.table.update()

        ui.notify(f"{len(self.files)} 件のファイルを読み込みました", type="positive")

    def target_files(self) -> list:
        if self.target == "all":
            return self.files
        rows = self.table.selected
        return rows
    
    def music_file_for_path(self, path: str) -> dict|None:
        if not path:
            return None
        return next((d for d in self.files if d["path"] == path), None)
        
    def analyzed(self, result: dict) -> None:
        result_files = result.get("result", [])
        for music_file in self.files:
            info = next((d for d in result_files if d["path"] == music_file["path"]), None)
            if info is None:
                continue
            music_file["bpm"] = info.get("bpm", music_file["bpm"])
            music_file["keyscale"] = info.get("keyscale", music_file["keyscale"])
            music_file["timesignature"] = info.get("timesignature", music_file["timesignature"])
            music_file["duration"] = info.get("duration", music_file["duration"])
        self.table.rows = self.files
        self.table.update()
    
    def transcripted(self, result: dict) -> None:
        result_files = result.get("result", [])
        for music_file in self.files:
            info = next((d for d in result_files if d["path"] == music_file["path"]), None)
            if info is None:
                continue
            music_file["lyrics"] = info.get("lyrics", music_file["lyrics"])
        self.table.rows = self.files
        self.table.update()
        
        
    def save_metadata(self) -> None:
        dicts = self.table.rows
        if len(dicts)==0:
            ui.notify("処理対象がありません")
            return
        files = [MusicFile.from_dict(item) for item in dicts]
        for file in files:
            if self.save_json:
                file.save_to_json()
            if self.save_lyrics:
                file.save_to_lyrics()
            if self.save_aitk:
                file.save_to_aitk()
        ui.notify("保存しました", type="positive")
        
    def set_metadata(self, key: str, val: str ) -> None:
        targets = self.target_files()
        if len(targets)==0:
            ui.notify("処理対象がありません")
            return
        for tgt in targets:
            result = next((item for item in self.files if item.get("name") == tgt.get("name")), None)
            if result != None:
                result[key] = val
        self.table.rows = self.files
        self.table.update()

    def set_lang(self, val: str) -> None:
        self.set_metadata("language", val)

    def set_caption(self, val: str) -> None:
        self.set_metadata("caption", val)

_worker: Worker = Worker()

@ui.page("/")
def main_page():
    ctx = MusicCtx()

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
    

    ui.add_css('''
.q-table th, .q-table td {
    padding: 2px 2px;
}

.brdr {
    border: 1px solid #ccc;
}
''')
    ui.markdown(f"## {ctx.name}")
    ui.label("ACE-Step向けのメタデータを書き出すwebuiです")
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
        ui.label("処理対象ファイルを ACE-Step Transcriber で解析し、歌詞を取得します")
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
            ui.button(icon="reload", on_click=lambda: ace_models.set_options(acestep_transcriber_models())).props('flat')
            ui.button(icon="setting", on_click=lambda: model_dir_panel.set_visibility(True)).props('flat')
            ui.space()
            ui.button("歌詞を解析する", on_click=transcript).bind_enabled_from(ctx.worker, "can_run")

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
                "style": 'white-space: nowrap; overflow: hidden;text-overflow: ellipsis;max-width:200px',
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
            
    # ═══════════════════════════════════════════════════════════════════════════════
    # 処理中UI
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.footer(bordered=True).bind_visibility_from(ctx.worker, "is_running").style('background-color: #f2f2f2'):
        with ui.row().classes("items-center gap-4"):
            ui.button("処理を中止する", on_click=ctx.worker.request_cancel).bind_visibility_from(
                ctx.worker, "is_running"
            ).props('color="orange"').tooltip("現在の処理が済んだら終了")
            ui.button("処理を即時中止する", icon='warning', on_click=ctx.worker.terminate_now).bind_visibility_from(
                ctx.worker, "is_running"
            ).props('color="red"').tooltip("強制的に子プロセスを終了")
            ui.label().style('color: #010101').bind_text_from(ctx.worker, "status")
        ui.linear_progress(show_value=False).props("instant-feedback").bind_value_from(
            ctx.worker, "progress"
        ).bind_visibility_from(ctx.worker, "is_running")

    with ui.page_sticky(position='top', y_offset=120) as model_dir_panel:
        def save_and_close_model_root_path_input():
            cnfg.set_models_dir(model_root_path_input.value)
            model_dir_panel.set_visibility(False)
        with ui.card():
            model_root_path_input = (
                ui.input(
                    value = str(cnfg.models_dir),
                    placeholder="フォルダのパスを入力...",
                )
                .props('style="min-width: 500px"')
                .props("clearable")
            )
            with ui.row().classes("items-center gap-4").classes('w-full justify-end'):
                ui.button('キャンセル', on_click=lambda e: model_dir_panel.set_visibility(False))
                ui.button("設定", on_click=save_and_close_model_root_path_input)

    model_dir_panel.set_visibility(False)


def main() -> None:
    parser = argparse.ArgumentParser(description="ACE-Step向けのメタデータを書き出すwebuiです")
    parser.add_argument("--host", default="127.0.0.1", help="default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=7869, help="default: 7869")
    parser.add_argument("--native", action="store_true", help="ブラウザでなくネイティブウィンドウで開く")
    parser.add_argument("--auto-reload", default=True, action="store_true", help="ソースコードが編集されたら自動でリロードする")

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
