from nicegui import ui


def show_error_dialog(txt: str) -> ui.dialog:
    """エラーメッセージを表示するダイアログを生成して open する。"""
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-120"):
        ui.markdown(txt)
        with ui.row().classes("w-full justify-end"):
            ui.button("OK", on_click=dialog.delete)
    return dialog


async def show_input_dialog(txt: str, placeholder: str = "") -> str | None:
    """入力ダイアログを生成して open し、OK なら入力テキストを返す。キャンセルなら None を返す。"""
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-120"):
        ui.markdown(txt)
        input_field = ui.input(placeholder=placeholder).props("outlined dense").classes("w-full")
        input_field.on("keydown.enter", lambda: dialog.submit(input_field.value))
        with ui.row().classes("w-full justify-end"):
            ui.button("キャンセル", on_click=lambda: dialog.submit(None))
            ui.button("OK", on_click=lambda: dialog.submit(input_field.value))
    dialog.open()
    await ui.run_javascript(f"document.getElementById('c{input_field.id}').focus()")
    return await dialog


async def show_confirm_dialog(txt: str) -> bool:
    """確認ダイアログを生成して open し、ユーザーの選択を待って True/False を返す。"""
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-120"):
        ui.markdown(txt)
        with ui.row().classes("w-full justify-end"):
            ui.button("キャンセル", on_click=lambda: dialog.submit(False))
            ui.button("OK", on_click=lambda: dialog.submit(True))
    return await dialog
