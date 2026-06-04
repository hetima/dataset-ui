import sys
from pathlib import Path
from nicegui import binding, ui
from common.setting import cnfg
from voice.voice_app_ctx import VoiceCtx
from common.xterm_dialog import XtermDialog

def tab_setting(ctx: VoiceCtx):
    # ═══════════════════════════════════════════════════════════════════════════════
    # 出力パス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("書き出しパス", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("成果物を書き出すフォルダパスを入力してください")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            outputs_path_input = ui.input(
                value=str(cnfg.outputs_dir),
                label="outputs path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button(
                "保存",
                on_click=lambda: ctx.set_outputs_dir(outputs_path_input.value),
            )

    # ═══════════════════════════════════════════════════════════════════════════════
    # モデルパス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("モデルパス", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("モデルをダウンロードするフォルダパスを入力してください")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            model_root_path_input = ui.input(
                value=str(cnfg.models_dir),
                label="models root path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button(
                "保存",
                on_click=lambda: ctx.set_models_root(model_root_path_input.value),
            )

    # ═══════════════════════════════════════════════════════════════════════════════
    # トレーニングパス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("トレーニングパス", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("トレーニングデータを配置するフォルダパスを入力してください")
        with ui.row().classes("items-center gap-4").classes("w-full"):
            train_path_input = ui.input(
                value=str(cnfg.train_dir),
                label="train path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button(
                "保存",
                on_click=lambda: ctx.set_train_dir(train_path_input.value or ""),
            )

    # ═══════════════════════════════════════════════════════════════════════════════
    # モデル選択
    # ═══════════════════════════════════════════════════════════════════════════════
    def irodori_tts_download_finished(success: bool) -> None:
        reload_irodori_tts_model()

    def irodori_tts_download(repo_id: str) -> None:
        cli = str(Path(__file__).parent.parent / "common" / "cli_task_download_repo.py")
        dlg = XtermDialog(
            args=[sys.executable, cli],
            title="ダウンロード",
            input_json={
                "repo_id": repo_id,
                "output_dir": str(cnfg.models_dir / "irodori-tts"),
            },
            finish_callback=irodori_tts_download_finished,
        )
        dlg.open()

    def irodori_tts_models() -> list[str]:
        models_dir = cnfg.models_dir / "irodori-tts"
        if not models_dir.exists():
            return []
        return [p.name for p in models_dir.iterdir() if p.is_dir()]

    with ui.expansion("Irodori-TTS モデルダウンロード", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):
        ui.label(
            "モデルの選択、ダウンロードを行います。トレーニングや推論に必要です。必ずダウンロードしてください"
        )
        ui.label(
            "「ダウンロード」を押すとモデルフォルダにダウンロードされます。"
            "ダウンロードが途中で止まる場合は、hf-xetをアンインストールすると改善する場合があります（pip uninstall hf-xet）。それでも駄目な場合は手動でダウンロードして配置してください。「モデルフォルダ/irodori-tts/Irodori-TTS-500M-v3/model.safetensors」と配置してください。"
        ).classes("infotxt")
        with ui.row().classes("items-center gap-4"):
            opt = irodori_tts_models()
            val = cnfg.voice.irodori_tts_model
            if not val in opt:
                val = opt[0] if len(opt) > 0 else ""
            irodoti_tts_model_input = (
                ui.input(
                    label="irodori-tts model",
                    placeholder="モデルを選択、または入力",
                    on_change=lambda e: setattr(e.sender, "value", e.value),
                )
                .props('style="min-width: 300px" outlined')
                .bind_value(cnfg.voice, "irodori_tts_model")
            )
            with irodoti_tts_model_input.add_slot("append"):
                with ui.button(icon="arrow_drop_down").props("flat").classes("padd4"):
                    ace_models_menu = ui.menu()

    def reload_irodori_tts_model():
        def hf_menu_item(models: list, repo_id: str):
            rid = repo_id.split("/")[-1]
            if rid not in models:
                with ui.item(
                    on_click=lambda: [
                        setattr(irodoti_tts_model_input, "value", repo_id),
                        ace_models_menu.close(),
                    ]
                ).classes("padd8 items-center"):
                    ui.item_section(repo_id)
                    ui.button(
                        "ダウンロード",
                        on_click=lambda: irodori_tts_download(repo_id),
                    ).props("flat dense color=primary").style("margin-left: 8px").on(
                        "click", js_handler="(e) => e.stopPropagation()"
                    )
            else:
                ui.menu_item(
                    repo_id,
                    lambda: setattr(irodoti_tts_model_input, "value", repo_id),
                ).classes("padd8")

        models = irodori_tts_models()
        ace_models_menu.clear()
        local_added = False
        with ace_models_menu:
            for model in models:
                ui.menu_item(
                    model, lambda m=model: setattr(irodoti_tts_model_input, "value", m)
                ).classes("padd8")
                local_added = True
            if local_added:
                ui.separator()
            ui.menu_item("from huggingface").classes("padd8").enabled = False
            # ACE-Step/acestep-transcriber
            hf_menu_item(models, "Aratako/Irodori-TTS-500M-v3")
            hf_menu_item(models, "Aratako/Irodori-TTS-600M-v3-VoiceDesign")
            ui.separator()
            ui.menu_item("メニューを更新", lambda: reload_irodori_tts_model()).classes(
                "padd8"
            )

    reload_irodori_tts_model()

    # ═══════════════════════════════════════════════════════════════════════════════
    # dataset_dirs
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("データセットフォルダ", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label(
            "データセットが配置されているフォルダを登録すると、簡単に呼び出すことが出来ます。データセット自体ではなくひとつ上のフォルダを登録してください。登録したフォルダに含まれるサブフォルダを選択できるようになります。"
        )
        with ui.row().classes("items-center gap-4").classes("w-full"):
            dataset_dir_input = ui.input(
                label="dataset path",
                placeholder="フォルダのパスを入力...",
            ).props('style="min-width: 500px" outlined')
            ui.button("追加", on_click=lambda: add_dataset_dir(dataset_dir_input.value))
        dataset_dirs = ui.list().props("bordered separator").classes("padd4 w-full")

        def add_dataset_dir(path: str|None):
            if path and ctx.add_dataset_dir(path):
                dataset_dir_input.value = ""

        def update_dataset_dirs():
            def _list_item(path: str, disable_up = "", disable_down = ""):
                with ui.item().classes("padd2"):
                    with ui.item_section().props("side"):
                        with ui.row().classes("gap-0"):
                            ui.button(
                                icon="arrow_upward",
                                on_click=lambda p=path: ctx.shift_dataset_dir(
                                    p, up=True  # type: ignore
                                ),
                            ).props(f"flat dense size=sm{disable_up}")
                            ui.button(
                                icon="arrow_downward",
                                on_click=lambda p=path: ctx.shift_dataset_dir(
                                    p, up=False  # type: ignore
                                ),
                            ).props(f"flat dense size=sm{disable_down}")
                    with ui.item_section():
                        ui.item_label(path)
                    with ui.item_section().props("side"):
                        ui.button(
                            icon="delete",
                            on_click=lambda p=path: ctx.delete_dataset_dir(p), # type: ignore
                        ).props("flat dense color=negative")

            dataset_dirs.clear()
            with dataset_dirs:
                disable_up = " disable"
                last_index = len(cnfg.voice.dataset_dirs) - 1

                for i, itm in enumerate(cnfg.voice.dataset_dirs):
                    disable_down = " disable" if i == last_index else ""
                    _list_item(itm, disable_up, disable_down)
                    disable_up = ""

        update_dataset_dirs()
        ctx.dataset_dirs_refresh_func.append(update_dataset_dirs)
