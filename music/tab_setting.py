from pathlib import Path
from nicegui import binding, ui
from music.setting import cnfg
from music.app_ctx import MusicCtx


def tab_setting(ctx: MusicCtx):

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

        def add_dataset_dir(path: str):
            if ctx.add_dataset_dir(path):
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
                last_index = len(cnfg.dataset_dirs) - 1

                for i, itm in enumerate(cnfg.dataset_dirs):
                    disable_down = " disable" if i == last_index else ""
                    _list_item(itm, disable_up, disable_down)
                    disable_up = ""

        update_dataset_dirs()
        ctx.dataset_dirs_refresh_func.append(update_dataset_dirs)
