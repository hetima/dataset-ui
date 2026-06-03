import sys
from pathlib import Path
from nicegui import ui
from common.setting import cnfg
from voice.voice_app_ctx import VoiceCtx
from common.xterm_view import XtermView

IRODORI_TRAIN_SUB_DIR = "irodori"

def tab_iridori_train(ctx: VoiceCtx):

    # ═══════════════════════════════════════════════════════════════════════════════
    # Load files
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("データセット作成", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        ui.label("データセットの検証と作成を行います。「データセットフォルダ/irodori/プロジェクト名」に作成されます。")
        with ui.row().classes("items-center gap-2"):
            path_input = (
                ui.textarea(
                    value="",
                    label="dataset paths",
                    placeholder="フォルダのパスを入力。複数のフォルダに対応しています。改行で区切ってください",
                    on_change=lambda e: setattr(e.sender, "value", e.value),
                )
                .props('autogrow style="min-width: 500px" outlined clearable')
                .classes("w-160")
            )
            project_name = ui.input(label="プロジェクト名", placeholder="my_lora", value="").props(
                "outlined style='width: 200px;'"
            )
            ui.button("データセット検証", on_click=lambda: validate_dataset(path_input.value))  # type: ignore
            ui.button("データセット生成", on_click=lambda: create_dataset(path_input.value, project_name.value))  # type: ignore

        xterm = XtermView(title="ターミナル").classes("w-full")

    def dataset_paths(text:str) -> list[Path]:
        """strを改行で区切ってリストにして返す。エラーがあったらnotifyして空配列を返す"""
        paths = text.split("\n")
        paths = [Path(p.strip()) for p in paths if p.strip()]
        for path in paths:
            if not path.exists():
                ui.notify(f"フォルダが見つかりません: {path}", type="negative")
                return []
            if path.is_relative_to(cnfg.train_dir):
                ui.notify(f"トレーニングフォルダ内のフォルダは指定できません: {path}", type="negative")
                return []
        return paths

    def validate_dataset(src_path: str):
        if not src_path:
            ui.notify("フォルダのパスを入力してください", type="warning")
            return 
        paths = dataset_paths(src_path)
        if len(paths) == 0:
            return

    def create_dataset(src_path: str, project_name: str):
        if not src_path:
            ui.notify("フォルダのパスを入力してください", type="warning")
            return 
        if not project_name:
            ui.notify("プロジェクト名を入力してください", type="warning")
            return
        paths = dataset_paths(src_path)
        if len(paths) == 0:
            return
