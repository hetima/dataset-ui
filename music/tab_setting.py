from pathlib import Path
from nicegui import binding, ui
from music.setting import cnfg
from music.app_ctx import MusicCtx


def tab_setting(ctx: MusicCtx):

    # ═══════════════════════════════════════════════════════════════════════════════
    # モデルパス設定
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion('モデルパス', value=True).classes('rounded-borders brdr overflow-hidden w-full').props('header-class="bg-grey-2 text-black"'):
        ui.label("モデルをダウンロードするフォルダパスを入力してください")
        with ui.row().classes("items-center gap-4").classes('w-full'):
            model_root_path_input = (
                ui.input(
                    value = str(cnfg.models_dir),
                    label="models root path",
                    placeholder="フォルダのパスを入力...",
                )
                .props('style="min-width: 500px" outlined')
            )
            ui.button("保存", on_click=lambda: ctx.set_models_root(model_root_path_input.value))

    # ═══════════════════════════════════════════════════════════════════════════════
    # dataset_dirs
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("データセットフォルダ", value=True).classes('rounded-borders brdr overflow-hidden w-full').props('header-class="bg-grey-2 text-black"'):
        ui.label("データセットが配置されているフォルダを登録すると、簡単に呼び出すことが出来ます。データセット自体ではなくひとつ上のフォルダを登録してください。登録したフォルダに含まれるサブフォルダを選択できるようになります。")
        with ui.row().classes("items-center gap-4").classes('w-full'):
            dataset_dir_input = (
                ui.input(
                    label="dataset path",
                    placeholder="フォルダのパスを入力...",
                )
                .props('style="min-width: 500px" outlined')
            )
            ui.button("追加", on_click=lambda: add_dataset_dir(dataset_dir_input.value))
        dataset_dirs = ui.list().props('bordered separator').classes('padd4 w-full')
        
        def add_dataset_dir(path: str):
            if ctx.add_dataset_dir(path):
                dataset_dir_input.value = ""
        
        def update_dataset_dirs():
            def _list_item(path: str):
                with ui.item().classes('padd2'):
                    ui.item(path).classes('padd2')
            
            dataset_dirs.clear()
            with dataset_dirs:
                for itm in cnfg.dataset_dirs:
                    _list_item(itm)
  
        update_dataset_dirs()
        ctx.dataset_dirs_refresh_func.append(update_dataset_dirs)
            

