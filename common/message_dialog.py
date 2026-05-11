from nicegui import ui


def show_error_dialog(txt: str) -> ui.dialog:
    """エラーメッセージを表示するダイアログを生成して open する。"""
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-120"):
        ui.markdown(txt)
        with ui.row().classes("w-full justify-end"):
            ui.button("OK", on_click=dialog.delete)
    return dialog


async def show_confirm_dialog(txt: str) -> bool:
    """確認ダイアログを生成して open し、ユーザーの選択を待って True/False を返す。"""
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-120"):
        ui.markdown(txt)
        with ui.row().classes("w-full justify-end"):
            ui.button("キャンセル", on_click=lambda: dialog.submit(False))
            ui.button("OK", on_click=lambda: dialog.submit(True))
    return await dialog
