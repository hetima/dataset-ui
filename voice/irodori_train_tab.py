import sys
from pathlib import Path
from nicegui import ui
from common.setting import cnfg
from voice.voice_app_ctx import VoiceCtx
from common.xterm_view import XtermView

IRODORI_SUB_DIR = "irodori-tts"
IRODORI_PHASE_SUB_DIR = "irodori-tts_phase"
IRODORI_LORA_SUB_DIR = "irodori-tts_lora"
IRODORI_SPIN_SUB_DIR = "irodori-tts_spin"

def tab_iridori_train(ctx: VoiceCtx):

    ui.markdown(
        f"**トレーニングデータ保存パス** → `{cnfg.train_dir.as_posix()}/irodori-tts/プロジェクト名`<br>"
        f"**トレーニング結果保存パス** → `{cnfg.models_dir.as_posix()}/irodori-tts/プロジェクト名`"
    )

    # ═══════════════════════════════════════════════════════════════════════════════
    # トレーニングデータ作成
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("トレーニングデータ作成", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        ui.label("データセットの検証とトレーニングデータ作成を行います。複数のフォルダをまとめてひとつのトレーニングデータを作成できます")
        ui.label("「トレーニングパス/irodori-tts/プロジェクト名」に作成されます。この工程には 書き起こし.txt または mtdt.json が必要です。メインタブで生成してください。transcript が必須で capiton と speaker_id はオプションです。").classes("infotxt")
        ui.label("最大音長（秒数）を指定すると、長いファイルはその秒数で切り詰められます。0にしておけばそのまま使用します").classes("infotxt")
        with ui.row().classes("items-center gap-2"):
            path_input = (
                ui.textarea(
                    value="",
                    label="dataset paths",
                    placeholder="フォルダのパスを入力。複数のフォルダに対応しています。改行で区切ってください",
                )
                .props('autogrow style="min-width: 500px" outlined clearable')
                .classes("w-160")
            )
            validate_dataset_btn = ui.button("データ検証", on_click=lambda: validate_dataset(path_input.value)) # type: ignore
            project_name = ui.input(label="プロジェクト名", placeholder="my_lora", value="").props(
                "outlined style='width: 200px;'"
            )
            max_seconds = ui.input(label="最大音長", placeholder="秒数", value="0").props(
                "outlined style='width: 80px;'"
            )
            create_dataset_btn =ui.button("データセット生成", on_click=lambda: create_dataset(path_input.value, project_name.value, max_seconds.value)) # type: ignore

        xterm = XtermView(title="ターミナル", rows=10).classes("w-full")
        validate_dataset_btn.bind_enabled(xterm, "is_idle")
        create_dataset_btn.bind_enabled(xterm, "is_idle")

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
        cli = str(Path(__file__).parent / "cli_task_irodori_validate.py")
        xterm.run(
            args=[sys.executable, cli],
            input_json=[str(path) for path in paths],
        )

    def create_dataset(src_path: str, project_name: str, max_seconds_str: str):
        if not src_path:
            ui.notify("フォルダのパスを入力してください", type="warning")
            return 
        if not project_name:
            ui.notify("プロジェクト名を入力してください", type="warning")
            return
        paths = dataset_paths(src_path)
        if len(paths) == 0:
            return
        output_dir = str(cnfg.train_dir / IRODORI_SUB_DIR / project_name)
        try:
            max_seconds = float(max_seconds_str) if max_seconds_str else 0
        except ValueError:
            ui.notify("最大音長は数値で入力してください", type="warning")
            return
        if max_seconds < 0:
            max_seconds = 0
        cli = str(Path(__file__).parent / "cli_task_iridori_prepare.py")
        input_json = {
            "paths": [str(path) for path in paths],
            "output_path": output_dir,
            "max_seconds": max_seconds if max_seconds > 0 else None,
        }
        xterm.run(
            args=[sys.executable, cli],
            input_json=input_json,
        )

    # ═══════════════════════════════════════════════════════════════════════════════
    # トレーニング
    # ═══════════════════════════════════════════════════════════════════════════════

    PRIORITY_MODELS = ["Irodori-TTS-500M-v3/model.safetensors", "Irodori-TTS-600M-v3-VoiceDesign/model.safetensors"]

    def list_safetensors(official_only: bool = True) -> list[str]:
        """models_dir/irodori-tts 以下の .safetensors をサブパス形式でリストアップ。優先モデルを先頭に並べる。"""
        base = cnfg.models_dir / IRODORI_SUB_DIR
        if not base.exists():
            return []
        all_paths = sorted(
            str(p.relative_to(base)).replace("\\", "/")
            for p in base.rglob("*.safetensors")
            if not p.name.endswith(".speaker.safetensors")
        )
        if official_only:
            return [p for p in PRIORITY_MODELS if p in all_paths]
        priority = [p for p in PRIORITY_MODELS if p in all_paths]
        rest = [p for p in all_paths if p not in PRIORITY_MODELS]
        return priority + rest

    def copy_train_command():
        cmd = build_train_command()
        if cmd is None:
            return
        ui.run_javascript(f"navigator.clipboard.writeText({cmd!r})")
        ui.notify("コマンドをコピーしました")

    with ui.expansion("トレーニング実行", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        ui.label(
            "Speaker Inversion トレーニングを行います。設定タブでモデルのダウンロードを済ませておいてください。"
        )
        ui.label(
            "実行コマンドをコピーできるようにしていますので、PowerShellやcmdで実行してください。venvのpython.exeを指定してるのでアクティベートしなくても実行できます。実行されるコマンドはカスタム版で、Ctrl+Cを送信するとその時点のステップを保存してから終了します。"
        ).classes("infotxt")
        with ui.row().classes("items-center gap-4"):
            config_select = ui.select(
                label="トレーニングの種類",
                options={
                    "train_500m_v3_speaker_inversion.yaml": "Speaker Inversion",
                    "train_500m_v3_lora.yaml": "Lora",
                    "train_500m_v3_voice_design_lora.yaml": "VoiceDesign Lora",
                    # "train_500m_v3_phase1_body.yaml": "Base phase1 body",
                    # "train_500m_v3_phase2_duration.yaml": "Base phase2 duration",
                    # "train_500m_v3_voice_design_phase1_body.yaml": "VD phase1 body",
                    # "train_500m_v3_voice_design_phase2_duration.yaml": "VD phase2 duration",
                },
                value="train_500m_v3_speaker_inversion.yaml",
            ).props("outlined style='width: 220px;'")

            model_input = ui.input(
                label="ベースモデル",
                placeholder="モデルを選択、または入力",
                value="Irodori-TTS-500M-v3/model.safetensors",
            ).props('style="min-width: 400px" outlined')
            with model_input.add_slot("append"):
                with ui.button(icon="arrow_drop_down").props("flat").classes("padd4"):
                    train_model_menu = ui.menu()

            dataset_input = (
                ui.input(
                    label="トレーニングデータ",
                    placeholder="データセットを選択、または入力",
                )
                .props('style="width: 250px" outlined')
            )
            custom_putput_name = (
                ui.input(label="カスタム出力名", placeholder="")
                .props("outlined style='width: 120px;'")
                .tooltip("空白にすればトレーニングデータ名を使用します")
            )
            with dataset_input.add_slot("append"):
                with ui.button(icon="arrow_drop_down").props("flat").classes("padd4"):
                    train_dataset_menu = ui.menu()
        with ui.row().classes("items-center gap-4"):
            auto_resume_check = ui.checkbox("--auto-resume").classes("ml-0")
            auto_resume_check.tooltip(
                "前回のチェックポイントがあれば自動で再開します。Speaker Inversionでは使えません"
            )
            auto_resume_check.set_enabled(False)
            def on_config_select_change(e):
                auto_resume_check.set_enabled(e.value != "train_500m_v3_speaker_inversion.yaml")
                if "voice_design" in e.value:
                    model_input.set_value("Irodori-TTS-600M-v3-VoiceDesign/model.safetensors")
                else:
                    model_input.set_value("Irodori-TTS-500M-v3/model.safetensors")
            config_select.on_value_change(on_config_select_change)

            max_steps_input = ui.input(label="--max-steps", placeholder="").props(
                "outlined style='width: 120px;'"
            ).tooltip("空白にすればデフォルト値を使用します")
            batch_size_input = (
                ui.input(label="--batch-size", placeholder="")
                .props("outlined style='width: 120px;'")
                .tooltip("空白にすればデフォルト値を使用します")
            )

            config_save_method = ui.select(
                label="保存間隔",
                options={
                    "default": "指定なし",
                    "step": "ステップ数",
                    "min": "時間（分）",
                },
                value="default",
            ).props("outlined style='width: 150px;'")
            config_save_interval = (
                ui.input(label="ステップ数", placeholder="")
                .props("outlined style='width: 120px;'")
                .tooltip("左のセレクトに従いステップ数か時間間隔（単位：分）を入力")
            )
            config_save_method.on_value_change(
                lambda e: config_save_interval.set_label(
                    config_save_method.options[e.value]
                )
            )

        with ui.row().classes("items-center gap-4 mt-2"):
            ui.button("トレーニングコマンドをコピー", on_click=copy_train_command)
            putput_dir_info = ui.label("").classes("infotxt")

    def reload_train_model_menu():
        models = list_safetensors()
        train_model_menu.clear()
        with train_model_menu:
            for m in models:
                ui.menu_item(
                    m, lambda v=m: setattr(model_input, "value", v)
                ).classes("padd8")
            if models:
                ui.separator()
            ui.menu_item("メニューを更新", lambda: reload_train_model_menu()).classes("padd8")

    def list_train_datasets() -> list[str]:
        """train_dir/irodori-tts 直下のフォルダをリストアップ。"""
        base = cnfg.train_dir / IRODORI_SUB_DIR
        if not base.exists():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir())

    def reload_train_dataset_menu():
        datasets = list_train_datasets()
        train_dataset_menu.clear()
        with train_dataset_menu:
            for d in datasets:
                ui.menu_item(
                    d, lambda v=d: setattr(dataset_input, "value", v)
                ).classes("padd8")
            if datasets:
                ui.separator()
            ui.menu_item("メニューを更新", lambda: reload_train_dataset_menu()).classes("padd8")

    reload_train_model_menu()
    reload_train_dataset_menu()

    def build_train_command() -> str | None:
        dataset = (dataset_input.value or "").strip()
        model = (model_input.value or "").strip()
        config = config_select.value or ""
        if not dataset:
            ui.notify("トレーニングデータを選択してください", type="warning")
            return None
        if not model:
            ui.notify("ベースモデルを選択してください", type="warning")
            return None
        if not config:
            ui.notify("トレーニングの種類を選択してください", type="warning")
            return None
        save_method = config_save_method.value
        save_interval = config_save_interval.value
        save_method_str = ""
        if not save_method or save_method == "default":
            save_method_str = ""
        elif not save_interval:
            ui.notify("保存間隔を入力するか指定なしを選んでください" + save_method, type="warning")
            return None
        if save_method == "step" and save_interval:
            save_method_str = " --save-every " + save_interval
        elif save_method == "min" and save_interval:
            save_method_str = " --save-interval-minutes " + save_interval
        model_name = dataset
        if custom_putput_name.value:
            model_name = custom_putput_name.value

        init_ckpt = f' --init-checkpoint "{cnfg.models_dir / IRODORI_SUB_DIR / model}"'

        model_sub_dir = IRODORI_SUB_DIR
        if "phase1" in config:
            model_sub_dir = IRODORI_PHASE_SUB_DIR
        elif "phase2" in config:
            init_ckpt = f' --init-checkpoint-dir "{cnfg.models_dir / IRODORI_PHASE_SUB_DIR / model_name}"'
            pass
        elif "speaker_inversion" in config:
            model_sub_dir = IRODORI_SPIN_SUB_DIR
        elif "lora" in config:
            model_sub_dir = IRODORI_LORA_SUB_DIR

        voice_dir = Path(__file__).parent.resolve()
        repo_root = voice_dir.parent

        train_script = repo_root / "cli" / "irodori_train.py"
        config_yaml = repo_root / "configs" / "irodoritts" / config
        manifest = cnfg.train_dir / IRODORI_SUB_DIR / dataset / "train_manifest.jsonl"
        output_dir = cnfg.models_dir / model_sub_dir / model_name

        auto_resume = " --auto-resume" if auto_resume_check.value else ""
        max_steps = " --max-steps " + max_steps_input.value.strip() if max_steps_input.value else ""
        batch_size = " --batch-size " + batch_size_input.value.strip() if batch_size_input.value else ""

        putput_dir_info.set_text(f"出力先: {output_dir.as_posix()}")
        return (
            f'{sys.executable} "{train_script}"'
            f' --manifest "{manifest}"'
            f' --output-dir "{output_dir}"'
            f' --config "{config_yaml}"'
            f"{init_ckpt}{auto_resume}{max_steps}{batch_size}{save_method_str}"
        )

