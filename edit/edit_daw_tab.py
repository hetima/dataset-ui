from nicegui import ui
from edit.edit_app_ctx import EditCtx


def tab_main(ctx: EditCtx):
    frame_container = ui.element("div").classes("w-full")

    def update_frame() -> None:
        """DAW iframe を現在の URL で描画する。"""

        element_id = f"c{frame_container.id}"
        if not ctx.daw_url:
            ui.run_javascript(
                f'''
                const dawContainer = document.getElementById("{element_id}");
                if (dawContainer) {{
                    dawContainer.innerHTML =
                        '<div class="infotxt">ファイルを選択して DAW を開いてください</div>';
                }}
                '''
            )
            return
        ui.run_javascript(
            f'''
            const dawContainer = document.getElementById("{element_id}");
            if (dawContainer) {{
                dawContainer.innerHTML =
                    '<iframe src="{ctx.daw_url}" style="width: 100%; height: 78vh; border: 1px solid #ccc; border-radius: 4px;"></iframe>';
            }}
            '''
        )

    ctx.daw_refresh_func.append(update_frame)
    ui.timer(0.1, update_frame, once=True)



