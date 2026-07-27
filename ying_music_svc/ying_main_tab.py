from pathlib import Path

from nicegui import ui

from common.setting import cnfg
from common.thread_task_dialog import ThreadTaskDialog
from ying_music_svc.task_ying_infer import run_ying_infer
from ying_music_svc.ying_app_ctx import YingCtx


RELOAD_VALUE = "__reload__"
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3"}


def tab_main(_ctx: YingCtx):
    def models_dir() -> Path:
        return Path(cnfg.ying.repository_dir) / "models"

    def project_options() -> dict[str, str]:
        base = models_dir()
        options: dict[str, str] = {}
        if base.is_dir():
            for path in sorted(base.iterdir(), key=lambda p: p.name.casefold()):
                if path.is_dir():
                    options[str(path)] = path.name
        options[RELOAD_VALUE] = "再読み込み"
        return options

    def lora_options(project: str | None) -> dict[str, str]:
        options: dict[str, str] = {}
        if project and Path(project).is_dir():
            base = Path(project)
            for path in sorted(base.rglob("*.lora.pth")):
                if path.is_file():
                    options[str(path)] = path.relative_to(base).as_posix()
        options[RELOAD_VALUE] = "再読み込み"
        return options

    def ref_options(project: str | None) -> dict[str, str]:
        options: dict[str, str] = {}
        if project and Path(project).is_dir():
            base = Path(project)
            for path in sorted(base.rglob("*")):
                if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                    options[str(path)] = path.relative_to(base).as_posix()
        options[RELOAD_VALUE] = "再読み込み"
        return options

    def reload_projects() -> None:
        project_select.set_options(project_options(), value=None)
        lora_select.set_options(lora_options(None), value=None)
        ref_select.set_options(ref_options(None), value=[])

    def reload_project_files() -> None:
        project = project_select.value
        lora_select.set_options(lora_options(project), value=None)
        ref_select.set_options(ref_options(project), value=[])

    def on_project_change(e) -> None:
        if e.value == RELOAD_VALUE:
            reload_projects()
            return
        reload_project_files()

    def on_lora_change(e) -> None:
        if e.value == RELOAD_VALUE:
            lora_select.set_options(lora_options(project_select.value), value=None)

    def on_ref_change(e) -> None:
        values = e.value if isinstance(e.value, list) else []
        if RELOAD_VALUE in values:
            ref_select.set_options(ref_options(project_select.value), value=[])

    def start_inference() -> None:
        source = (source_input.value or "").strip()
        if len(source) >= 2 and source[0] == source[-1] and source[0] in "\"'":
            source = source[1:-1]
        base_checkpoint = (base_checkpoint_input.value or "").strip()
        project = project_select.value
        lora = lora_select.value
        refs = ref_select.value if isinstance(ref_select.value, list) else []

        if not source:
            ui.notify("ソース音声を指定してください", type="warning")
            return
        if not base_checkpoint:
            ui.notify("ベースcheckpointを指定してください", type="warning")
            return
        if not project or project == RELOAD_VALUE:
            ui.notify("Projectを選択してください", type="warning")
            return
        if not lora or lora == RELOAD_VALUE:
            ui.notify("LoRAを選択してください", type="warning")
            return
        refs = [ref for ref in refs if ref != RELOAD_VALUE]
        if not refs:
            ui.notify("参照音声を選択してください", type="warning")
            return

        try:
            steps = int(steps_input.value or 30)
        except (TypeError, ValueError):
            ui.notify("拡散ステップ数は整数で入力してください", type="warning")
            return

        data = {
            "repository_dir": cnfg.ying.repository_dir,
            "venv_dir": cnfg.ying.venv_dir,
            "source": source,
            "base_checkpoint": base_checkpoint,
            "lora": lora,
            "refs": refs,
            "lora_scale": float(
                lora_scale.value if lora_scale.value is not None else 1.0
            ),
            "steps": steps,
            "pitch_shift": (
                int(pitch_shift.value or 0) if pitch_shift_enabled.value else None
            ),
            "format": format_select.value or "flac",
            "output_path": str(cnfg.outputs_dir),
        }
        ThreadTaskDialog(
            fn=run_ying_infer,
            data=data,
            title=f"YingMusic-SVC 推論 ({len(refs)}件)",
        ).open()

    with ui.expansion("YingMusic-SVC 推論", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        ui.label("YingMusic-SVCの推論を実行します。結果はdataset-uiの書き出しフォルダに保存されます。進行状況は本物のターミナルを参照してください。").classes("infotxt")
        ui.label("このページではLoRAを使用した推論のみ対応しています。").classes("infotxt")
        source_input = ui.input(
            label="ソース音声",
            placeholder="変換する音声ファイルのパス",
        ).props("outlined").classes("w-full")
        base_checkpoint_input = ui.input(
            label="ベースcheckpoint",
            value=str(
                Path(cnfg.ying.repository_dir)
                / "models"
                / "YingMusic-SVC-full.pt"
            ),
            placeholder="ベースcheckpointのパス",
        ).props("outlined").classes("w-full")

        project_select = ui.select(
            options=project_options(),
            label="Project",
        ).props("outlined dense options-dense").classes("w-full")
        lora_select = ui.select(
            options=lora_options(None),
            label="LoRA",
        ).props("outlined dense options-dense").classes("w-full")
        ref_select = ui.select(
            options=ref_options(None),
            value=[],
            label="参照音声",
            multiple=True,
        ).props("outlined dense options-dense use-chips").classes("w-full")

        project_select.on_value_change(on_project_change)
        lora_select.on_value_change(on_lora_change)
        ref_select.on_value_change(on_ref_change)

        with ui.row().classes("items-center gap-4 w-full"):
            with ui.column().classes("gap-1"):
                ui.label("LoRA適用倍率").classes("text-xs")
                with ui.row().classes("items-center gap-2"):
                    lora_scale = ui.slider(
                        min=0, max=2, step=0.05, value=1.0
                    ).classes("w-48")
                    ui.label().bind_text_from(
                        lora_scale,
                        "value",
                        lambda v: f"{float(v):.2g}",
                    ).classes("w-6")

            steps_input = ui.input(
                label="拡散ステップ数",
                value="30",
            ).props("outlined dense").style("width: 160px")

            format_select = ui.select(
                options=["wav", "flac"],
                value="flac",
                label="フォーマット",
            ).props("outlined dense options-dense").style("width: 140px")

        with ui.row().classes("items-center gap-4 w-full"):
            pitch_shift_enabled = ui.checkbox("Pitch shiftを指定", value=False)
            pitch_shift = ui.slider(
                min=-12, max=12, step=1, value=0
            ).classes("w-64")
            ui.label().bind_text_from(
                pitch_shift,
                "value",
                lambda v: str(int(v)),
            ).classes("w-8")
            pitch_shift.bind_enabled_from(pitch_shift_enabled, "value")

        ui.button("推論", on_click=start_inference)
