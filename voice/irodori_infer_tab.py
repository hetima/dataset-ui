import asyncio
import dataclasses
import json
import sys
from datetime import datetime
from pathlib import Path
import httpx
from nicegui import background_tasks, helpers, ui
from common.setting import cnfg
from voice.voice_app_ctx import VoiceCtx

SERVER_URL = "http://127.0.0.1:7867"
KNOWN_MODELS = ["Irodori-TTS-500M-v3", "Irodori-TTS-600M-v3-VoiceDesign"]
IRODORI_LORA_SUB_DIR = "irodori-tts_lora"
LORA_NONE = ""
LORA_RELOAD = "__reload__"


@dataclasses.dataclass(frozen=True)
class InferJob:
    """Irodori-TTS 推論キューに積む設定一式。"""

    text: str
    lora_adapter: str | None
    cfg_scale_text: float
    cfg_scale_speaker: float
    num_steps: int
    response_format: str
    out_path: Path


def tab_iridori_infer(ctx: VoiceCtx):
    queue: asyncio.Queue[InferJob] = asyncio.Queue()
    state = {"current": None, "worker_started": False}
    lora_select_holder = {"value": None}

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

    def list_lora_adapters() -> dict[str, str]:
        """models_dir/irodori-tts_lora/*/checkpoint_* を選択肢として返す。"""
        base = cnfg.models_dir / IRODORI_LORA_SUB_DIR
        options = {LORA_NONE: "なし（デフォルト）"}
        if base.exists():
            paths = sorted(
                p
                for p in base.glob("*/checkpoint_*")
                if p.is_dir()
            )
            for path in paths:
                options[str(path)] = path.relative_to(base).as_posix()
        options[LORA_RELOAD] = "再読み込み"
        return options

    def normalize_path_text(path: str | None) -> str:
        """比較用にパス文字列を正規化する。"""
        if not path:
            return ""
        try:
            return str(Path(path).expanduser().resolve()).casefold()
        except Exception:
            return str(path).replace("/", "\\").casefold()

    def lora_base_checkpoint(adapter_path: str | None) -> str | None:
        """LoRA metadata から作成元ベースモデルの checkpoint path を読む。"""
        if not adapter_path:
            return None
        metadata_path = Path(adapter_path) / "irodori_lora_metadata.json"
        if not metadata_path.is_file():
            return None
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        base_init = data.get("base_init")
        if not isinstance(base_init, dict):
            return None
        checkpoint_path = base_init.get("checkpoint_path")
        return checkpoint_path if isinstance(checkpoint_path, str) else None

    def is_lora_compatible(adapter_path: str | None) -> bool:
        """サーバの起動中モデルと LoRA の作成元が違う場合は False を返す。"""
        base_checkpoint = lora_base_checkpoint(adapter_path)
        if not base_checkpoint:
            return True
        running, server_checkpoint = check_health()
        if not running or not server_checkpoint:
            return True
        return normalize_path_text(base_checkpoint) == normalize_path_text(server_checkpoint)

    def stem_exists(path: Path) -> bool:
        """同じ親フォルダに同じ stem のファイルがあるか調べる。"""
        if not path.parent.exists():
            return False
        return any(p.is_file() and p.stem == path.stem for p in path.parent.iterdir())

    def make_output_path(prefix: str, fmt: str) -> Path:
        """日時展開済みプレフィクスから出力ファイルパスを作る。"""
        expanded = datetime.now().strftime((prefix or "irodori").strip() or "irodori")
        relative = Path(expanded)
        parent = cnfg.outputs_dir / relative.parent
        stem = relative.name or "irodori"
        return parent / f"{stem}.{fmt}"

    def unique_output_path(path: Path) -> Path:
        """保存直前の実ファイル状態を見て、未使用の出力ファイルパスを作る。"""
        index = 0
        while True:
            stem = path.stem if index == 0 else f"{path.stem}_{index:02d}"
            candidate = path.with_name(f"{stem}{path.suffix}")
            if not stem_exists(candidate):
                return candidate
            index += 1

    def enqueue_infer():
        """UI の現在値をジョブ化して推論キューに追加する。"""
        text = (text_input.value or "").strip()
        if not text:
            ui.notify("テキストを入力してください", type="warning")
            return

        try:
            num_steps = max(1, int(float(num_steps_input.value or 40)))
        except ValueError:
            ui.notify("ステップ数は数値で入力してください", type="warning")
            return

        fmt = format_select.value or "wav"
        if fmt not in ("wav", "flac"):
            ui.notify("フォーマットを選択してください", type="warning")
            return

        cnfg.voice.save()
        out_path = make_output_path(cnfg.voice.irodori_tts_output_prefix, fmt)
        lora_select = lora_select_holder["value"]
        selected_lora = lora_select.value if lora_select else LORA_NONE
        if selected_lora and not is_lora_compatible(selected_lora):
            ui.notify(
                "選択した LoRA は起動中のベースモデルと違うモデルで作成されています。"
                "対応するモデルでサーバを起動し直してください。",
                type="warning",
            )
            return
        job = InferJob(
            text=text,
            lora_adapter=selected_lora if selected_lora and selected_lora != LORA_RELOAD else None,
            cfg_scale_text=float(cfg_scale_text_slider.value or 0),
            cfg_scale_speaker=float(cfg_scale_speaker_slider.value or 0),
            num_steps=num_steps,
            response_format=fmt,
            out_path=out_path,
        )
        queue.put_nowait(job)
        start_worker()
        queue_status.refresh()
        ui.notify(f"推論キューに追加しました: {out_path.name}")

    def clear_queue():
        """待機中の推論ジョブだけをキューから削除する。"""
        count = 0
        while True:
            try:
                job = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            queue.task_done()
            count += 1
        queue_status.refresh()
        ui.notify(f"待機中の推論を {count} 件クリアしました")

    def build_payload(job: InferJob) -> dict:
        """Irodori-TTS サーバへ送る JSON payload を作る。"""
        irodori = {
            "no_ref": True,
            "num_steps": job.num_steps,
            "cfg_scale_text": job.cfg_scale_text,
            "cfg_scale_speaker": job.cfg_scale_speaker,
        }
        if job.lora_adapter:
            irodori["lora_adapter"] = job.lora_adapter
        return {
            "model": "irodori-tts",
            "input": job.text,
            "response_format": job.response_format,
            "irodori": irodori,
        }

    async def worker():
        """推論キューを順番に処理し、返ってきた音声をファイルに保存する。"""
        while True:
            job = await queue.get()
            state["current"] = job
            queue_status.refresh()
            try:
                async with httpx.AsyncClient(timeout=600) as client:
                    res = await client.post(
                        f"{SERVER_URL}/v1/audio/speech",
                        json=build_payload(job),
                    )
                    try:
                        res.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        raise RuntimeError(res.text or str(exc)) from exc
                out_path = unique_output_path(job.out_path)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(res.content)
                ui.notify(f"推論結果を書き出しました: {out_path.name}")
            except Exception as exc:
                ui.notify(f"推論に失敗しました: {exc}", type="negative")
            finally:
                state["current"] = None
                queue.task_done()
                queue_status.refresh()

    def start_worker():
        """推論ワーカーを必要な時に一度だけ起動する。"""
        if state["worker_started"]:
            return
        state["worker_started"] = True
        background_tasks.create(
            helpers.await_with_context(worker(), ui.context.client),
            name="irodori_infer_worker",
        )

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
                    "Irodori-TTS サーバ起動方法：モデルを選択し、コマンドをコピーボタンを押して、クリップボードにコピーされたコマンドをターミナルで実行してください。"
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

    # ═══════════════════════════════════════════════════════════════════════════════
    # 推論
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("推論", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"')as infer_expansion:
        text_input = ui.textarea(label="テキスト").props("outlined autogrow").classes("w-full")

        @ui.refreshable
        def lora_select_view():
            def on_lora_change(e):
                if e.value == LORA_RELOAD:
                    lora_select = lora_select_holder["value"]
                    if lora_select is None:
                        return
                    lora_select.set_value(LORA_NONE)
                    lora_select_view.refresh()

            lora_select = ui.select(
                options=list_lora_adapters(),
                value=LORA_NONE,
                label="LoRA選択",
            ).props("outlined dense options-dense").classes("w-full")
            lora_select_holder["value"] = lora_select
            lora_select.on_value_change(on_lora_change)

        lora_select_view()

        with ui.row().classes("items-center gap-4 w-full"):
            with ui.column().classes("gap-1"):
                ui.label("cfg_scale_text").classes("text-sm")
                with ui.row().classes("items-center gap-2"):
                    cfg_scale_text_slider = (
                        ui.slider(min=0, max=10, step=0.1, value=3.0)
                        .props("label")
                        .classes("w-56")
                    )
                    ui.label().bind_text_from(cfg_scale_text_slider, "value", lambda v: f"{v:.1f}")
            with ui.column().classes("gap-1"):
                ui.label("cfg_scale_speaker").classes("text-sm")
                with ui.row().classes("items-center gap-2"):
                    cfg_scale_speaker_slider = (
                        ui.slider(min=0, max=10, step=0.1, value=5.0)
                        .props("label")
                        .classes("w-56")
                    )
                    ui.label().bind_text_from(cfg_scale_speaker_slider, "value", lambda v: f"{v:.1f}")

        with ui.row().classes("items-center gap-4"):
            num_steps_input = ui.number(label="ステップ数", value=40, min=1, format="%d").props(
                "outlined dense style='width: 120px;'"
            )
            prefix_input = ui.input(
                label="プレフィクス",
                value=cnfg.voice.irodori_tts_output_prefix,
            ).props("outlined dense style='width: 260px;'")
            prefix_input.bind_value(cnfg.voice, "irodori_tts_output_prefix")
            format_select = ui.select(
                options=["wav", "flac"],
                value="wav",
                label="フォーマット",
            ).props("outlined dense options-dense style='width: 140px;'")
            ui.button("推論", on_click=enqueue_infer)

        @ui.refreshable
        def queue_status():
            current = state["current"]
            with ui.column().classes("gap-1 w-full"):
                with ui.row().classes("items-center gap-4"):
                    ui.label(f"推論：")
                    ui.label(f"待機中: {queue.qsize()} 件")
                    if current:
                        ui.label(f"処理中: {current.out_path.name}")
                    else:
                        ui.label("処理中: なし")
                    ui.button("キューをクリア", on_click=clear_queue).props("dense").set_enabled(queue.qsize() > 0)
        with infer_expansion.add_slot("header"):
            queue_status()



