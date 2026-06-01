import json
from pathlib import Path
from nicegui import binding, ui
from common.setting import cnfg
from common.cpu_task_dialog import CpuTaskDialog
from common.message_dialog import show_confirm_dialog
from music.music_app_ctx import MusicCtx
from roformer.roformer import list_roformer_models, list_known_models
from roformer.task_download import download_roformer_model

def tab_setting(ctx: MusicCtx):
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

        def add_dataset_dir(path: str | None):
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
                last_index = len(cnfg.music.dataset_dirs) - 1

                for i, itm in enumerate(cnfg.music.dataset_dirs):
                    disable_down = " disable" if i == last_index else ""
                    _list_item(itm, disable_up, disable_down)
                    disable_up = ""

        update_dataset_dirs()
        ctx.dataset_dirs_refresh_func.append(update_dataset_dirs)

    # ═══════════════════════════════════════════════════════════════════════════════
    # roformer モデル管理
    # ═══════════════════════════════════════════════════════════════════════════════
    with (
        ui.expansion("roformer モデル管理", value=True)
        .classes("rounded-borders brdr overflow-hidden w-full")
        .props('header-class="bg-grey-2 text-black"')
    ):
        ui.label("手動でモデルを追加する場合は、「モデルフォルダ/roformer」フォルダに入れてください。サブフォルダにも対応してます。config.yaml がある場合はモデルと同じ名前にしてください。")
        ui.label("ダウンロードがどうしても途中で止まる場合はwebブラウザとかで直接ダウンロードしてください。ごめんなさい。")
        with ui.row().classes("w-full gap-4 items-start"):
            # 左：インストール済みモデル
            with ui.column().classes("flex-1 gap-1"):
                ui.label("インストール済みモデル").classes("font-bold")
                with ui.scroll_area().classes("brdr").style("height: 520px; width: 100%"):
                    installed_col = ui.column().classes("w-full gap-0")

            # 右：既知モデル一覧
            with ui.column().classes("flex-1 gap-1"):
                ui.label("既知モデル一覧").classes("font-bold")
                with ui.scroll_area().classes("brdr").style("height: 520px; width: 100%"):
                    known_col = ui.column().classes("w-full gap-0")

        def download_model(m: dict):
            data = {
                "repo_id": m["repo_id"],
                "filename": m["filename"],
                "yamlname": m.get("config", ""),
                "output_dir": str(Path(cnfg.models_dir) / "roformer"),
                "convert": False,
                "metadata": m,
            }
            CpuTaskDialog(
                fn=download_roformer_model,
                data=data,
                title=f"ダウンロード: {m['display_name']}",
                finish_callback=lambda ok, _: refresh_roformer() if ok else None,
            ).open()

        async def delete_model(m: dict):
            path = Path(m["path"])
            if not await show_confirm_dialog(f"削除しますか？（ゴミ箱に移動します）\n\n{path.name}"):
                return
            try:
                from send2trash import send2trash
            except ImportError:
                ui.notify("send2trash pipライブラリが見つかりません", type="negative")
                return
            for p in [path, path.with_suffix(".yaml"), path.with_suffix(".meta.json")]:
                if p.exists():
                    send2trash(str(p))
            refresh_roformer()

        def _format_file_size(path: Path) -> str:
            size_bytes = path.stat().st_size
            if size_bytes >= 1024 ** 3:
                return f"{size_bytes / 1024 ** 3:.1f}GB"
            return f"{size_bytes // (1024 ** 2)}MB"

        async def show_info_dialog(m: dict):
            path = Path(m["path"])
            meta_path = path.with_suffix(".meta.json")

            result = {"ok": False}
            with ui.dialog() as dlg, ui.card().classes("w-120"):
                ui.label(f"モデル情報: {path.stem}").classes("font-bold text-base")
                ui.label(str(path)).classes("text-xs infotxt")
                display_name_input = ui.input(
                    label="表示名 (display_name)",
                    value=m["name"],
                ).props('outlined style="min-width: 400px"').classes("w-full")
                output_suffix_input = ui.input(
                    label="出力サフィックス (output_suffix)",
                    value=m.get("output_suffix", ""),
                ).props("outlined").classes("w-full").tooltip(
                    "suffixが空のとき自動で使われます。どのモデルで出力したか分かりやすくなります。例: _vocals"
                )
                with ui.row().classes("justify-end gap-2 w-full"):
                    ui.button("キャンセル", on_click=dlg.close).props("flat")
                    def on_ok():
                        result["ok"] = True
                        dlg.close()
                    ui.button("OK", on_click=on_ok).props("color=primary")

            dlg.open()
            await dlg
            if not result["ok"]:
                return

            new_name = (display_name_input.value or "").strip() or path.stem
            new_suffix = output_suffix_input.value or ""

            # meta.json を読み込み or 新規作成
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            else:
                meta = {"size": _format_file_size(path)}

            meta["display_name"] = new_name
            meta["output_suffix"] = new_suffix
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            refresh_roformer()

        def refresh_roformer():
            installed_col.clear()
            with installed_col:
                for m in list_roformer_models():
                    with ui.row().classes("items-center gap-2 q-px-sm padd4 w-full"):
                        ui.label(m["name"]).classes("flex-1 text-sm")
                        ui.label(m.get("size", "")).classes("text-xs infotxt")
                        ui.button("情報", on_click=lambda _, m=m: show_info_dialog(m)).props(
                            "flat dense size=sm"
                        )
                        ui.button("削除", on_click=lambda _, m=m: delete_model(m)).props(
                            "flat dense color=negative size=sm"
                        )

            known_col.clear()
            with known_col:
                for m in list_known_models():
                    with ui.row().classes("items-center gap-2 q-px-sm padd4 w-full"):
                        ui.label(m["display_name"]).classes("flex-1 text-sm")
                        ui.label(m.get("size", "")).classes("text-xs infotxt")
                        if not m["exists"]:
                            ui.button(icon="download", on_click=lambda m=m: download_model(m)).props("flat dense color=primary size=sm") # type: ignore

        refresh_roformer()
        ctx.model_refresh_func.append(refresh_roformer)
