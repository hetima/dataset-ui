from nicegui import ui
from edit.edit_app_ctx import EditCtx


def tab_main(ctx: EditCtx):
    ui.markdown(
        "**S** 再生位置でオーディオイベントを分割<br>**R** 再生位置でコンピングリージョンを分割<br>**SPACE** 再生/停止（再生開始位置に戻る）<br>**ENTER** 再生/一時停止<br>**L** ループ再生オンオフ（波形ビューを右方向にドラッグで選択範囲を作ります。コンピングモードで選択範囲を作るには下側2割くらいのスペースでドラッグしてください）"
    )

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
                const dawFrame = dawContainer.querySelector("iframe");
                if (!dawFrame || dawFrame.getAttribute("src") !== "{ctx.daw_url}") {{
                    dawContainer.innerHTML =
                        '<iframe src="{ctx.daw_url}" style="width: 100%; height: 90vh; border: 1px solid #ccc; border-radius: 4px;"></iframe>';
                }}
            }}
            '''
        )

    ctx.daw_refresh_func.append(update_frame)
    ui.timer(0.1, update_frame, once=True)
