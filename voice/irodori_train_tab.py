import sys
from pathlib import Path
from nicegui import ui
from common.setting import cnfg
from voice.voice_app_ctx import VoiceCtx

IRODORI_TRAIN_SUB_DIR = "irodori"

def tab_iridori_train(ctx: VoiceCtx):

    # ═══════════════════════════════════════════════════════════════════════════════
    # Load files
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("データセット", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        with ui.row().classes("items-center gap-2"):
            path_input = (
                ui.input(
                    value=cnfg.voice.last_dataset_path,
                    label="dataset path",
                    placeholder="フォルダのパスを入力...",
                    on_change=lambda e: setattr(e.sender, "value", e.value),
                )
                .props('style="min-width: 500px" outlined clearable')
                .classes("w-140")
            )
            project_name = ui.input(label="プロジェクト名", placeholder="my_lora", value="").props(
                "outlined style='width: 200px;'"
            )
            ui.button("データセット生成", on_click=lambda: create_dataset(path_input.value, project_name.value)) # type: ignore

    def create_dataset(src_path: str, project_name: str):
        if not src_path:
            ui.notify("フォルダのパスを入力してください", type="warning")
            return
        if not project_name:
            ui.notify("プロジェクト名を入力してください", type="warning")
            return
        src_path_path = Path(src_path)
        if not src_path_path.exists():
            ui.notify("フォルダが見つかりません", type="negative")
            return
        should_copy = True
        if src_path_path.is_relative_to(cnfg.train_dir):
            ui.notify("トレーニングフォルダ内のフォルダは指定できません", type="negative")
            return

