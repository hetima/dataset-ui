import sys
from pathlib import Path
import httpx
from nicegui import ui
from voice.voice_app_ctx import VoiceCtx

SERVER_URL = "http://127.0.0.1:7867"
KNOWN_MODELS = ["Irodori-TTS-500M-v3", "Irodori-TTS-600M-v3-VoiceDesign"]


def tab_iridori_infer(ctx: VoiceCtx):

    def check_health() -> tuple[bool, str | None]:
        """サーバの /health を叩いて (起動中か, model.checkpoint) を返す。"""
        try:
            res = httpx.get(f"{SERVER_URL}/health", timeout=2.0)
            if res.status_code != 200:
                return False, None
            data = res.json()
            if data.get("status") != "ok":
                return False, None
            return True, data.get("model", {}).get("checkpoint")
        except Exception:
            return False, None

    def build_launch_command(model_name: str) -> str:
        """サーバ起動コマンドの文字列を組み立てる。"""
        cli = Path(__file__).parent.parent / "cli" / "irodori_server.py"
        return f'{sys.executable} "{cli}" --model-path {model_name}'

    def copy_launch_command(model_name: str):
        cmd = build_launch_command(model_name)
        ui.run_javascript(f"navigator.clipboard.writeText({cmd!r})")
        ui.notify("コマンドをコピーしました")

    # ═══════════════════════════════════════════════════════════════════════════════
    # サーバステータス
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("サーバステータス", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):

        @ui.refreshable
        def status_card():
            running, model_id = check_health()
            with ui.column():
                with ui.row().classes("items-center gap-2"):
                    ui.button("ステータス更新", on_click=lambda: status_card.refresh())
                    if running:
                        ui.label("起動しています")
                        ui.label(f"model: {model_id}")
                    else:
                        ui.label("起動していません")
                ui.label(
                    "Irodori TTS サーバ起動方法：モデルを選択し、コマンドをコピーボタンを押して、クリップボードにコピーされたコマンドをターミナルで実行してください。"
                    "起動完了したら更新ボタンを押して確認してください。"
                ).classes("infotxt")
                with ui.row().classes("items-center gap-2"):
                    model_select = ui.select(
                        KNOWN_MODELS, value=KNOWN_MODELS[0], label="モデル"
                    ).props("outlined dense options-dense style='width: 280px;'")
                    ui.button(
                        "起動コマンドをコピー",
                        on_click=lambda: copy_launch_command(model_select.value),
                    )

        status_card()
