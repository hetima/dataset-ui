from nicegui import ui

from common.daw_view import daw_view
from edit.edit_app_ctx import EditCtx


def tab_main(ctx: EditCtx):
    ui.markdown(
        "**S** 再生位置でオーディオイベントを分割"
        "<br>**R** 再生位置でコンピングリージョンを分割<br>"
        "**SPACE** 再生/停止（再生開始位置に戻る）<br>"
        "**ENTER** 再生/一時停止"
        "<br>**L** ループ再生オンオフ（波形ビューを右方向にドラッグで選択範囲を作ります。コンピングモードで選択範囲を作るには下側2割くらいのスペースでドラッグしてください）<br>"
        "<br>"
        "コンピングモードではリージョンが存在する箇所のみ再生され、存在しない箇所はミュートされます。<br>"
        "<br>"
        "書き出し時にはマスターボリュームの数値は無視されます。<br>"
        "AAFファイルにはファイルのフルパスで記入されます。書き出し後にファイルを移動すると見失います。<br>"
        "品質を重視するならAAFで書き出してちゃんとしたDAWで作業することをお勧めします。"
    )

    daw_view(lambda: ctx.daw_url, ctx.daw_refresh_func, ctx.daw_post_message_func)
