from nicegui import ui


def show_error_dialog(txt: str) -> ui.dialog:
    """エラーメッセージを表示するダイアログを生成して open する。"""
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-120"):
        ui.label(txt)
        with ui.row().classes("w-full justify-end"):
            ui.button("OK", on_click=dialog.delete)
    return dialog


