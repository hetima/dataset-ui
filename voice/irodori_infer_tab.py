import asyncio
import re
import dataclasses
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import httpx
from send2trash import send2trash
from mutagen.flac import FLAC
from mutagen.id3 import COMM, USLT
from mutagen.wave import WAVE
from nicegui import app, background_tasks, helpers, ui
from common.nicegui_plyr_alt import PlyrAltControl, plyr_alt, plyr_alt_control
from common.setting import cnfg
from voice.voice_app_ctx import VoiceCtx

SERVER_URL = "http://127.0.0.1:7867"
KNOWN_MODELS = ["Irodori-TTS-500M-v3", "Irodori-TTS-600M-v3-VoiceDesign"]
IRODORI_LORA_SUB_DIR = "irodori-tts_lora"
LORA_NONE = ""
LORA_RELOAD = "__reload__"
VOICE_NONE = ""
VOICE_RELOAD = "__reload__"
IRODORI_RESULT_MEDIA_ROUTE = "/irodori-result-media"
_IRODORI_RESULT_MEDIA_ROUTES: set[str] = set()


@dataclasses.dataclass(frozen=True)
class InferJob:
    """Irodori-TTS 推論キューに積む設定一式。"""

    text: str
    voice: str | None
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
    voice_select_holder = {"value": None}
    result_control = PlyrAltControl()
    result_list_holder: dict[str, ui.column | None] = {"value": None}

    def check_health() -> tuple[bool, str | None]:
        """サーバーの /health を叩いて (起動中か, model.checkpoint) を返す。"""
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
        """サーバー起動コマンドの文字列を組み立てる。"""
        cli = Path(__file__).parent.parent / "cli" / "irodori_server.py"
        return f'{sys.executable} "{cli}" --model-path {model_name}'

    def copy_launch_command(model_name: str):
        cmd = build_launch_command(model_name)
        ui.run_javascript(f"navigator.clipboard.writeText({cmd!r})")
        ui.notify("コマンドをコピーしました", position="bottom-right")

    def list_server_voices() -> dict[str, str]:
        """Irodori-TTS サーバーの voice 一覧を選択肢として返す。"""
        options = {VOICE_NONE: "なし"}
        try:
            res = httpx.get(f"{SERVER_URL}/v1/audio/voices", timeout=3.0)
            res.raise_for_status()
            data = res.json()
            for item in data.get("data", []):
                voice_id = item.get("id")
                if isinstance(voice_id, str) and voice_id:
                    options[voice_id] = voice_id
        except Exception:
            pass
        options[VOICE_RELOAD] = "メニューを更新"
        return options

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
        """サーバーの起動中モデルと LoRA の作成元が違う場合は False を返す。"""
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

    def make_output_path(prefix: str, fmt: str, *, voice: str | None = None, lora: str | None = None, steps: int | None = None) -> Path:
        """日時展開済みプレフィクスから出力ファイルパスを作る。%voice %lora %step を置換する。"""
        lora_safe = "_".join(Path(lora).parts[-2:]) if lora else ""
        text = (prefix or "irodori").strip() or "irodori"
        text = text.replace("%voice", voice or "").replace("%lora", lora_safe).replace("%step", str(steps) if steps is not None else "")
        expanded = datetime.now().strftime(text.strip() or "irodori")
        relative = Path(expanded)
        parent = cnfg.outputs_dir / relative.parent
        stem = re.sub(r'[:*?"<>|]', "_", relative.name) or "irodori"
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

    def media_url_for_file(path: Path) -> str:
        """保存済み音声ファイルをブラウザから読める URL に変換する。"""
        resolved = path.resolve()
        parent = resolved.parent
        route_id = hashlib.sha1(str(parent).encode("utf-8")).hexdigest()[:10]
        route = f"{IRODORI_RESULT_MEDIA_ROUTE}/{route_id}"
        if route not in _IRODORI_RESULT_MEDIA_ROUTES:
            app.add_media_files(route, str(parent))
            _IRODORI_RESULT_MEDIA_ROUTES.add(route)
        return f"{route}/{quote(resolved.name)}"

    def format_result_params(job: InferJob, seed: str | None) -> str:
        """生成結果欄に表示する推論パラメータを短く整形する。"""
        voice = job.voice or "なし"
        lora = "なし"
        if job.lora_adapter:
            lora_path = Path(job.lora_adapter)
            lora = "/".join(lora_path.parts[-2:])
        return (
            f"steps={job.num_steps}, "
            f"cfg_text={job.cfg_scale_text:g}, cfg_speaker={job.cfg_scale_speaker:g}, "
            f"seed={seed or ''}, voice={voice}, lora={lora}"
        )

    def add_result_player(path: Path, job: InferJob, seed: str | None):
        """生成結果欄の末尾に PlyrAlt プレイヤーと推論情報を追加する。"""
        result_list = result_list_holder["value"]
        if result_list is None:
            return
        with result_list:
            with ui.column().classes("w-full gap-1 mb-3") as section:
                with ui.row().classes("w-full items-center gap-2"):
                    with ui.element("div").classes("flex-1 min-w-0"):
                        plyr_alt(
                            media_url_for_file(path),
                            path.name,
                            control=result_control,
                        )
                    delete_btn = ui.button(icon="delete").props("flat square dense color=grey")

                    def on_delete_click(btn=delete_btn, p=path, s=section):
                        if btn.text == "削除する":
                            send2trash(p)
                            s.delete()
                        else:
                            btn.text = "削除する"
                            btn.props("color=negative")

                    delete_btn.on_click(on_delete_click)
                ui.label(f"入力: {job.text}").classes(
                    "w-full text-xs text-grey-9"
                ).style("white-space: pre-wrap; overflow-wrap: anywhere;")
                ui.label(f"パラメータ: {format_result_params(job, seed)}").classes(
                    "w-full text-xs text-grey-8"
                ).style("overflow-wrap: anywhere;")

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
        voice_select = voice_select_holder["value"]
        selected_voice = voice_select.value if voice_select else VOICE_NONE
        lora_select = lora_select_holder["value"]
        selected_loras: list[str] = lora_select.value if lora_select else []
        # 有効なLoRAだけ残す（空リストの場合はLoRAなし1件として扱う）
        valid_loras: list[str | None] = [v for v in selected_loras if v and v not in (LORA_NONE, LORA_RELOAD)]
        lora_list: list[str | None] = valid_loras if valid_loras else [None]
        for lora in lora_list:
            if lora and not is_lora_compatible(lora):
                lora_path = Path(lora)
                lora_label = "/".join(lora_path.parts[-2:])
                ui.notify(
                    f"LoRA「{lora_label}」は起動中のベースモデルと違うモデルで作成されています。"
                    "対応するモデルでサーバーを起動し直してください。",
                    type="warning",
                )
                return
        voice_val = selected_voice if selected_voice and selected_voice != VOICE_RELOAD else None
        for lora in lora_list:
            out_path = make_output_path(cnfg.voice.irodori_tts_output_prefix, fmt, voice=voice_val, lora=lora, steps=num_steps)
            job_out_path = unique_output_path(out_path) if len(lora_list) > 1 else out_path
            job = InferJob(
                text=text,
                voice=voice_val,
                lora_adapter=lora,
                cfg_scale_text=float(cfg_scale_text_slider.value or 0),
                cfg_scale_speaker=float(cfg_scale_speaker_slider.value or 0),
                num_steps=num_steps,
                response_format=fmt,
                out_path=job_out_path,
            )
            queue.put_nowait(job)
        start_worker()
        queue_status.refresh()
        count = len(lora_list)
        msg = f"推論キューに{count}件追加しました" if count > 1 else f"推論キューに追加しました: {out_path.name}"
        ui.notify(msg, position="bottom-right")

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
        ui.notify(f"待機中の推論を {count} 件クリアしました", position="bottom-right")

    def build_payload(job: InferJob) -> dict:
        """Irodori-TTS サーバーへ送る JSON payload を作る。"""
        irodori = {
            "num_steps": job.num_steps,
            "cfg_scale_text": job.cfg_scale_text,
            "cfg_scale_speaker": job.cfg_scale_speaker,
        }
        if job.voice is None:
            irodori["no_ref"] = True
        if job.lora_adapter:
            irodori["lora_adapter"] = job.lora_adapter
        payload = {
            "model": "irodori-tts",
            "input": job.text,
            "response_format": job.response_format,
            "irodori": irodori,
        }
        if job.voice is not None:
            payload["voice"] = job.voice
        return payload

    def save_audio_metadata(path: Path, job: InferJob, seed: str | None) -> None:
        """生成音声に入力テキストと推論パラメータを書き込む。"""
        description = (
            f"cfg_scale_text:{job.cfg_scale_text}, "
            f"cfg_scale_speaker:{job.cfg_scale_speaker}, "
            f"seed:{seed or ''}"
        )
        if job.lora_adapter:
            lora_path = Path(job.lora_adapter)
            lora_label = "/".join(lora_path.parts[-2:])
            description += f" ,lora:{lora_label}"
        if job.response_format == "flac":
            audio = FLAC(path)
            audio["lyrics"] = job.text
            audio["description"] = description
            audio.save()
            return
        if job.response_format == "wav":
            audio = WAVE(path)
            if audio.tags is None:
                audio.add_tags()
            if audio.tags is not None:
                audio.tags.delall("USLT")
                audio.tags.delall("COMM")
                audio.tags.add(USLT(encoding=3, lang="jpn", desc="", text=job.text))
                audio.tags.add(COMM(encoding=3, lang="jpn", desc="", text=description))
                audio.save()

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
                seed = res.headers.get("X-Irodori-Seed")
                save_audio_metadata(out_path, job, seed)
                add_result_player(out_path, job, seed)
                ui.notify(f"推論結果を書き出しました: {out_path.name}", position="bottom-right")
            except Exception as exc:
                ui.notify(f"推論に失敗しました: {exc}", type="negative", position="bottom-right")
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
    # サーバーステータス
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("サーバーステータス", value=True).classes(
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
                    "Irodori-TTS サーバー起動方法：モデルを選択し、コマンドをコピーボタンを押して、クリップボードにコピーされたコマンドをターミナルで実行してください。"
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
        ui.label("推論サーバーで生成処理を行い書き出しフォルダに保存します。サーバーが起動していることを確認してください。LoRAを複数選択すると、同じパラメータのキューを複数実行します。ファイル名に %Y-%m-%d などの日付時刻フォーマットを入れると現在日時で置き換えられます。%voice %lora %step を入れると設定パラメータで置き換えられます。「/」を入れるとサブフォルダが作成されます。重複するファイル名は連番が付けられます。").classes("infotxt")
        text_input = ui.textarea(label="テキスト").props("outlined autogrow").classes("w-full")

        @ui.refreshable
        def lora_select_view():
            def on_lora_change(e):
                lora_select = lora_select_holder["value"]
                if lora_select is None:
                    return
                values: list = e.value if isinstance(e.value, list) else []
                if LORA_NONE in values:
                    lora_select.set_value([])
                elif LORA_RELOAD in values:
                    lora_select.set_value([])
                    lora_select_view.refresh()

            lora_select = ui.select(
                options=list_lora_adapters(),
                value=[],
                label="LoRA選択",
                multiple=True,
            ).props("outlined dense options-dense use-chips").classes("w-full")
            lora_select_holder["value"] = lora_select # type: ignore
            lora_select.on_value_change(on_lora_change)

        lora_select_view()

        @ui.refreshable
        def voice_select_view():
            def on_voice_change(e):
                if e.value == VOICE_RELOAD:
                    voice_select = voice_select_holder["value"]
                    if voice_select is None:
                        return
                    voice_select.set_value(VOICE_NONE)
                    voice_select_view.refresh()

            voice_select = ui.select(
                options=list_server_voices(),
                value=VOICE_NONE,
                label="voice",
            ).props("outlined dense options-dense style='width: 220px;'")
            voice_select_holder["value"] = voice_select # type: ignore
            voice_select.on_value_change(on_voice_change)

        voice_select_view()

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
                label="ファイル名",
                value=cnfg.voice.irodori_tts_output_prefix,
            ).props("outlined dense style='width: 320px;'")
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


    # ═══════════════════════════════════════════════════════════════════════════════
    # 生成結果
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("生成結果", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"')as infer_expansion:
        with ui.column().classes("w-full gap-2"):
            plyr_alt_control(result_control)
            result_list_holder["value"] = ui.column().classes("w-full gap-2")
