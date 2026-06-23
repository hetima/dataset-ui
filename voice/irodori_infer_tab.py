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
from common.nicegui_audioplayer_alt import PlyrAltControl, plyr_alt, plyr_alt_control
from common.nicegui_emoji_picker import attach_emoji_picker
from common.irodori_preset import IrodoriPreset
from common.message_dialog import show_input_dialog
from common.setting import cnfg
from voice.voice_app_ctx import VoiceCtx

EMOJI_JSON_PATH = Path(__file__).resolve().parent / "emoji.json"

SERVER_URL = "http://127.0.0.1:7867"
KNOWN_MODELS = ["Irodori-TTS-500M-v3", "Irodori-TTS-600M-v3-VoiceDesign"]
IRODORI_LORA_SUB_DIR = "irodori-tts_lora"
IRODORI_VOICES_SUB_DIR = "irodori-tts_voices"
LORA_EXPLICIT_NONE = "__none__"
LORA_RELOAD = "__reload__"
VOICE_EXPLICIT_NONE = "__none__"
VOICE_RELOAD = "__reload__"
REF_EMBED_RELOAD = "__reload__"
IRODORI_RESULT_MEDIA_ROUTE = "/irodori-result-media"
_IRODORI_RESULT_MEDIA_ROUTES: set[str] = set()


@dataclasses.dataclass(frozen=True)
class InferJob:
    """Irodori-TTS 推論キューに積む設定一式。"""

    text: str
    caption: str | None
    voice: str | None
    ref_embeds: tuple[str, str] | None
    ref_embed_weights: tuple[float, float] | None
    ref_embed_method: str
    lora_adapter: str | None
    lora_scale: float
    cfg_scale_text: float
    cfg_scale_speaker: float
    cfg_scale_caption: float
    num_steps: int
    response_format: str
    out_path: Path


def tab_iridori_infer(ctx: VoiceCtx):
    queue: asyncio.Queue[InferJob] = asyncio.Queue()
    state = {"current": None, "worker_started": False}
    lora_select_holder = {"value": None}
    lora_scale_holder = {"value": None}
    lora_scale_value = {"value": 1.0}
    server_model_state = {"voice_design": False}
    caption_value = {"value": ""}
    cfg_scale_values = {"text": 3.0, "speaker": 5.0}
    cfg_scale_caption_value = {"value": 3.0}
    voice_select_holder = {"value": None}
    mixed_ref_enabled = {"value": False}
    ref_embed_a_holder = {"value": None}
    ref_embed_b_holder = {"value": None}
    ref_embed_ratio_holder = {"value": None}
    ref_embed_method_holder = {"value": None}
    speaker_condition_values = {
        "voices": [],
        "ref_embed_a": None,
        "ref_embed_b": None,
        "ratio_a": 0.5,
        "method": "linear",
    }
    ref_embed_options = {"value": {REF_EMBED_RELOAD: "メニューを更新"}}
    voice_options = {"value": {VOICE_EXPLICIT_NONE: "なし（voiceなし）", VOICE_RELOAD: "メニューを更新"}}
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
        ui.notify("コマンドをコピーしました")

    def list_server_voices() -> dict[str, str]:
        """Irodori-TTS サーバーの voice 一覧を選択肢として返す。"""
        options = {VOICE_EXPLICIT_NONE: "なし（voiceなし）"}
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
        """models_dir/irodori-tts_lora 内の LoRA アダプターを選択肢として返す。"""
        base = cnfg.models_dir / IRODORI_LORA_SUB_DIR
        options = {LORA_EXPLICIT_NONE: "なし（LoRAなし）"}
        if base.exists():
            paths = sorted(
                metadata.parent
                for metadata in base.rglob("irodori_lora_metadata.json")
                if metadata.is_file()
            )
            for path in paths:
                options[str(path)] = path.relative_to(base).as_posix()
        options[LORA_RELOAD] = "再読み込み"
        return options

    def list_speaker_embeddings() -> dict[str, str]:
        """models_dir/irodori-tts_voices 内の Speaker Inversion を列挙する。"""
        base = cnfg.models_dir / IRODORI_VOICES_SUB_DIR
        options: dict[str, str] = {}
        if base.exists():
            for path in sorted(base.rglob("*.speaker.safetensors")):
                if path.is_file():
                    options[str(path.resolve())] = path.relative_to(base).as_posix()
        options[REF_EMBED_RELOAD] = "メニューを更新"
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

    def speaker_embedding_name(path: str) -> str:
        """Speaker Inversion のファイル名から表示用の名前を返す。"""
        suffix = ".speaker.safetensors"
        name = Path(path).name
        return name[:-len(suffix)] if name.endswith(suffix) else Path(path).stem

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
        ts = int(path.stat().st_mtime * 1000) if path.exists() else int(datetime.now().timestamp() * 1000)
        return f"{route}/{quote(resolved.name)}?t={ts}"

    def format_result_params(job: InferJob, seed: str | None) -> str:
        """生成結果欄に表示する推論パラメータを短く整形する。"""
        if job.ref_embeds and job.ref_embed_weights:
            voice = ", ".join(
                f"{speaker_embedding_name(path)}:{weight:g}"
                for path, weight in zip(
                    job.ref_embeds, job.ref_embed_weights, strict=True
                )
            )
        else:
            voice = job.voice
        params = (
            f"steps={job.num_steps}, "
            f"cfg_text={job.cfg_scale_text:g}, cfg_speaker={job.cfg_scale_speaker:g}, "
            f"seed={seed or ''}"
        )
        if voice:
            params += f", voice={voice}"
        if job.lora_adapter:
            lora_path = Path(job.lora_adapter)
            lora = "/".join(lora_path.parts[-2:])
            params += f", lora={lora}, lora_scale={job.lora_scale:g}"
        return params

    def add_result_player(path: Path, job: InferJob, seed: str | None):
        """生成結果欄の先頭に PlyrAlt プレイヤーと推論情報を追加する。"""
        result_list = result_list_holder["value"]
        if result_list is None:
            return
        with ui.column() as section:
            section.classes("w-full gap-1 mb-3")
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
        section.move(result_list, target_index=0)

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
        ref_embeds: tuple[str, str] | None = None
        ref_embed_weights: tuple[float, float] | None = None
        ref_embed_method = "linear"
        if mixed_ref_enabled["value"]:
            ref_embed_a = ref_embed_a_holder["value"]
            ref_embed_b = ref_embed_b_holder["value"]
            path_a = ref_embed_a.value if ref_embed_a else None
            path_b = ref_embed_b.value if ref_embed_b else None
            if not path_a or path_a == REF_EMBED_RELOAD or not path_b or path_b == REF_EMBED_RELOAD:
                ui.notify("混合する Speaker Inversion を2つ選択してください", type="warning")
                return
            if normalize_path_text(path_a) == normalize_path_text(path_b):
                ui.notify("異なる Speaker Inversion を選択してください", type="warning")
                return
            ratio_slider = ref_embed_ratio_holder["value"]
            ratio_a = float(ratio_slider.value if ratio_slider else 0.5)
            ref_embeds = (path_a, path_b)
            ref_embed_weights = (ratio_a, 1.0 - ratio_a)
            method_toggle = ref_embed_method_holder["value"]
            ref_embed_method = str(method_toggle.value if method_toggle else "linear")

        voice_select = voice_select_holder["value"]
        selected_voices: list[str] = voice_select.value if voice_select else []
        lora_select = lora_select_holder["value"]
        selected_loras: list[str] = lora_select.value if lora_select else []
        # 有効なLoRAだけ残す。EXPLICIT_NONEはNone（LoRAなし）に変換。空リストの場合はLoRAなし1件として扱う
        def _normalize_lora(v: str) -> str | None:
            return None if v == LORA_EXPLICIT_NONE else v
        valid_loras: list[str | None] = [_normalize_lora(v) for v in selected_loras if v not in (LORA_RELOAD,)]
        lora_list: list[str | None] = valid_loras if valid_loras else [None]
        # 有効なvoiceだけ残す。EXPLICIT_NONEはNone（voiceなし）に変換。空リストの場合はvoiceなし1件として扱う
        def _normalize_voice(v: str) -> str | None:
            return None if v == VOICE_EXPLICIT_NONE else v
        valid_voices: list[str | None] = [_normalize_voice(v) for v in selected_voices if v not in (VOICE_RELOAD,)]
        voice_list: list[str | None] = [None] if ref_embeds else (valid_voices if valid_voices else [None])
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
        # lora × voice の直積でジョブを積む
        jobs: list[InferJob] = []
        for lora in lora_list:
            for voice_val in voice_list:
                output_voice = voice_val
                if ref_embeds:
                    output_voice = "+".join(
                        speaker_embedding_name(path) for path in ref_embeds
                    )
                out_path = make_output_path(cnfg.voice.irodori_tts_output_prefix, fmt, voice=output_voice, lora=lora, steps=num_steps)
                job_out_path = unique_output_path(out_path) if (len(lora_list) * len(voice_list)) > 1 else out_path
                jobs.append(InferJob(
                    text=text,
                    caption=caption_value["value"].strip() if server_model_state["voice_design"] else None,
                    voice=voice_val,
                    ref_embeds=ref_embeds,
                    ref_embed_weights=ref_embed_weights,
                    ref_embed_method=ref_embed_method,
                    lora_adapter=lora,
                    lora_scale=float(
                        lora_scale_holder["value"].value
                        if lora_scale_holder["value"] is not None
                        else 1.0
                    ),
                    cfg_scale_text=float(cfg_scale_values["text"]),
                    cfg_scale_speaker=float(cfg_scale_values["speaker"]),
                    cfg_scale_caption=float(cfg_scale_caption_value["value"]),
                    num_steps=num_steps,
                    response_format=fmt,
                    out_path=job_out_path,
                ))
        for job in jobs:
            queue.put_nowait(job)
        start_worker()
        queue_status.refresh()
        count = len(jobs)
        msg = f"推論キューに{count}件追加しました" if count > 1 else f"推論キューに追加しました: {jobs[0].out_path.name}"
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
        if job.caption:
            irodori["caption"] = job.caption
            irodori["cfg_scale_caption"] = job.cfg_scale_caption
        if job.ref_embeds:
            irodori["ref_embeds"] = list(job.ref_embeds)
            irodori["ref_embed_weights"] = list(job.ref_embed_weights or ())
            irodori["ref_embed_method"] = job.ref_embed_method
        elif job.voice is None:
            irodori["no_ref"] = True
        if job.lora_adapter:
            irodori["lora_adapter"] = job.lora_adapter
            irodori["lora_scale"] = job.lora_scale
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
            description += f" ,lora:{lora_label}, lora_scale:{job.lora_scale}"
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
    ui.markdown(
        f"**モデルデータパス** → `{cnfg.models_dir.as_posix()}/irodori-tts`<br>"
        f"**LoRAパス** → `{cnfg.models_dir.as_posix()}/irodori-tts_lora`<br>"
        f"**Voicesパス** → `{cnfg.models_dir.as_posix()}/irodori-tts_voices`<br>"
    )

    # ═══════════════════════════════════════════════════════════════════════════════
    # サーバーステータス
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("サーバーステータス", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"'):

        _health: tuple[bool, str | None] = (False, None)

        @ui.refreshable
        def status_card():
            running, model_id = _health
            with ui.column():
                with ui.row().classes("items-center gap-2"):
                    async def on_refresh_click():
                        nonlocal _health
                        loop = asyncio.get_event_loop()
                        _health = await loop.run_in_executor(None, check_health)
                        server_model_state["voice_design"] = bool(
                            _health[1] and "voicedesign" in _health[1].casefold()
                        )
                        status_card.refresh()
                        caption_input_view.refresh()
                        cfg_scale_view.refresh()
                        if _health[0]:
                            voice_options["value"] = await loop.run_in_executor(None, list_server_voices)
                            speaker_condition_view.refresh()
                    ui.button("ステータス更新", on_click=on_refresh_click)
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

        async def _initial_health_check():
            nonlocal _health
            loop = asyncio.get_event_loop()
            _health = await loop.run_in_executor(None, check_health)
            server_model_state["voice_design"] = bool(
                _health[1] and "voicedesign" in _health[1].casefold()
            )
            status_card.refresh()
            caption_input_view.refresh()
            cfg_scale_view.refresh()
        ui.timer(0, _initial_health_check, once=True)

    # ═══════════════════════════════════════════════════════════════════════════════
    # 推論
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("推論", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"')as infer_expansion:
        ui.label("推論サーバーで生成処理を行い書き出しフォルダに保存します。サーバーが起動していることを確認してください。LoRAやVoiceを複数選択すると、それぞれのパラメータのキューを複数実行します。「なし」の項目を明示することで、不使用のキューを含ませることができます。ファイル名に %Y-%m-%d などの日付時刻フォーマットを入れると現在日時で置き換えられます。%voice %lora %step を入れると設定パラメータで置き換えられます。「/」を入れるとサブフォルダが作成されます。重複するファイル名は連番が付けられます。").classes("infotxt")
        ui.label("voice は上記 Voices パスに .wav や .flac や .speaker.safetensors ファイルを置くことで認識されます。").classes("infotxt")
        ui.label("テキストに「:」と入力すると絵文字補完のポップアップが表示されます。続けて入力（英語、ローマ字対応）していくと候補が絞られます↑↓キーで選択しEnterで入力できます。").classes("infotxt")
        # ── プリセット ───────────────────────────────────────────
        delete_confirm_state: dict[str, bool] = {}

        def apply_preset(p: dict) -> None:
            preset = IrodoriPreset.from_dict(p)
            warnings: list[str] = []

            text_input.set_value(preset.text)
            caption_value["value"] = preset.caption

            lora_sel = lora_select_holder["value"]
            if lora_sel is not None:
                available_lora = set(lora_sel.options.keys()) if isinstance(lora_sel.options, dict) else set(lora_sel.options)
                missing_lora = [v for v in preset.lora_adapter if v not in available_lora]
                valid_lora = [v for v in preset.lora_adapter if v in available_lora]
                lora_sel.set_value(valid_lora)
                if missing_lora:
                    warnings.append(f"LoRA: {', '.join(missing_lora)}")
            lora_scale_value["value"] = preset.lora_scale
            if lora_scale_holder["value"] is not None:
                lora_scale_holder["value"].set_value(preset.lora_scale)

            mixed_ref_enabled["value"] = preset.mixed_ref_enabled
            mixed_ref_checkbox.set_value(preset.mixed_ref_enabled)
            available_ref = set(ref_embed_options["value"].keys()) if isinstance(ref_embed_options["value"], dict) else set(ref_embed_options["value"])
            missing_ref: list[str] = []
            def _check_ref(val: str | None, label: str) -> str | None:
                if val is None or val in available_ref:
                    return val
                missing_ref.append(f"{label}: {val}")
                return None
            speaker_condition_values["ref_embed_a"] = _check_ref(preset.ref_embed_a, "モデルA")
            speaker_condition_values["ref_embed_b"] = _check_ref(preset.ref_embed_b, "モデルB")
            if missing_ref:
                warnings.append(f"Speaker Inversion ({', '.join(missing_ref)})")
            speaker_condition_values["ratio_a"] = preset.ratio_a
            speaker_condition_values["method"] = preset.ref_embed_method

            opts = voice_options["value"]
            available_voices = set(opts.keys()) if isinstance(opts, dict) else set(opts)
            missing_voices = [v for v in preset.voices if v not in available_voices]
            valid_voices = [v for v in preset.voices if v in available_voices]
            speaker_condition_values["voices"] = valid_voices
            if missing_voices:
                warnings.append(f"voice: {', '.join(missing_voices)}")

            speaker_condition_view.refresh()
            cfg_scale_text_slider.set_value(preset.cfg_scale_text)
            cfg_scale_speaker_slider.set_value(preset.cfg_scale_speaker)
            cfg_scale_values["text"] = preset.cfg_scale_text
            cfg_scale_values["speaker"] = preset.cfg_scale_speaker
            cfg_scale_caption_value["value"] = preset.cfg_scale_caption
            caption_input_view.refresh()
            cfg_scale_view.refresh()
            num_steps_input.set_value(preset.num_steps)
            format_select.set_value(preset.response_format)

            if warnings:
                ui.notify(f"プリセット「{preset.name}」を適用しました（見つからなかった項目: {' / '.join(warnings)}）", type="warning", timeout=6000)
            else:
                ui.notify(f"プリセット「{preset.name}」を適用しました")

        async def on_add_preset() -> None:
            name = await show_input_dialog("プリセット名を入力してください", placeholder="プリセット名")
            if not name or not name.strip():
                return
            name = name.strip()
            lora_sel = lora_select_holder["value"]
            preset = IrodoriPreset(
                name=name,
                text=text_input.value or "",
                caption=caption_value["value"],
                lora_adapter=list(lora_sel.value) if lora_sel else [],
                lora_scale=float(lora_scale_value["value"]),
                mixed_ref_enabled=mixed_ref_enabled["value"],
                ref_embed_a=speaker_condition_values.get("ref_embed_a"),
                ref_embed_b=speaker_condition_values.get("ref_embed_b"),
                ratio_a=float(speaker_condition_values.get("ratio_a", 0.5)),
                ref_embed_method=str(speaker_condition_values.get("method", "linear")),
                voices=list(speaker_condition_values.get("voices", [])),
                cfg_scale_text=float(cfg_scale_values["text"]),
                cfg_scale_speaker=float(cfg_scale_values["speaker"]),
                cfg_scale_caption=float(cfg_scale_caption_value["value"]),
                num_steps=int(float(num_steps_input.value or 40)),
                response_format=format_select.value or "wav",
            )
            cnfg.voice.add_irodori_preset(preset)
            preset_menu_view.refresh()
            ui.notify(f"プリセット「{name}」を保存しました")

        @ui.refreshable
        def preset_menu_view() -> None:
            delete_confirm_state.clear()
            with ui.row().classes("items-center"):
                preset_btn = ui.button("プリセット", icon="tune").props("flat dense")
                with preset_btn, ui.menu():
                    presets: list[dict] = cnfg.voice.irodori_presets
                    if not presets:
                        with ui.menu_item(auto_close=False):
                            ui.label("プリセットがありません").classes("text-grey-6 text-sm")
                    for p in presets:
                        pname: str = p.get("name", "")
                        with ui.menu_item(auto_close=False):
                            with ui.row().classes("items-center gap-2 w-full"):
                                ui.label(pname).classes("flex-1 cursor-pointer").on(
                                    "click", lambda _e, _p=p: apply_preset(_p)
                                )
                                trash_btn = ui.button(icon="delete").props(
                                    "flat dense size=sm color=grey"
                                )
                                def _on_trash(btn=trash_btn, name=pname):
                                    if delete_confirm_state.get(name):
                                        cnfg.voice.delete_irodori_preset(name)
                                        preset_menu_view.refresh()
                                    else:
                                        delete_confirm_state[name] = True
                                        btn.set_text("削除する")
                                        btn.props("color=negative")
                                trash_btn.on_click(_on_trash)
                    ui.separator()
                    with ui.menu_item(on_click=on_add_preset, auto_close=True):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("add")
                            ui.label("プリセットを追加")

        with ui.row().classes("justify-end w-full"):
            preset_menu_view()
        # ────────────────────────────────────────────────────────

        text_input = ui.textarea(label="テキスト").props("outlined autogrow").classes("w-full")
        attach_emoji_picker(text_input, EMOJI_JSON_PATH)

        @ui.refreshable
        def caption_input_view():
            if not server_model_state["voice_design"]:
                return
            caption_input = ui.textarea(
                label="キャプション",
                value=caption_value["value"],
            ).props("outlined autogrow").classes("w-full")
            caption_input.on_value_change(
                lambda e: caption_value.__setitem__("value", e.value or "")
            )

        caption_input_view()

        @ui.refreshable
        def lora_select_view():
            def on_lora_change(e):
                lora_select = lora_select_holder["value"]
                if lora_select is None:
                    return
                values: list = e.value if isinstance(e.value, list) else []
                if LORA_RELOAD in values:
                    lora_select.set_value([])
                    lora_select_view.refresh()

            with ui.row().classes("items-center gap-3 w-full no-wrap"):
                lora_select = ui.select(
                    options=list_lora_adapters(),
                    value=[],
                    label="LoRA選択",
                    multiple=True,
                ).props("outlined dense options-dense use-chips").classes("flex-grow")
                lora_select_holder["value"] = lora_select # type: ignore
                lora_select.on_value_change(on_lora_change)
                with ui.column().classes("gap-1"):
                    with ui.row().classes("items-center gap-1"):
                        ui.label("LoRA適用率").classes("text-xs")
                        ui.button(icon="restart_alt").props(
                            "flat dense round size=sm color=grey"
                        ).on_click(lambda: lora_scale_slider.set_value(1.0))
                    with ui.row().classes("items-center gap-2"):
                        lora_scale_slider = ui.slider(
                            min=0,
                            max=2,
                            step=0.05,
                            value=lora_scale_value["value"],
                        ).classes("w-48")
                        lora_scale_holder["value"] = lora_scale_slider # type: ignore
                        lora_scale_slider.on_value_change(
                            lambda e: lora_scale_value.__setitem__(
                                "value", float(e.value) # type: ignore
                            )
                        )
                        ui.label().bind_text_from(
                            lora_scale_slider,
                            "value",
                            lambda v: f"{float(v):.2g}",
                        ).classes("w-4")

        lora_select_view()

        @ui.refreshable
        def speaker_condition_view():
            if mixed_ref_enabled["value"]:
                async def reload_ref_embeds():
                    loop = asyncio.get_event_loop()
                    ref_embed_options["value"] = await loop.run_in_executor(
                        None, list_speaker_embeddings
                    )
                    speaker_condition_view.refresh()

                async def on_ref_embed_change(e):
                    if e.value == REF_EMBED_RELOAD:
                        await reload_ref_embeds()
                with ui.card().classes("gap-2 w-full"):
                    ui.label("ふたつの .speaker.safetensors を適用します。異なるモデルを選び、スライダーで割合を調整してください。").classes("infotxt")
                    with ui.row().classes("items-center gap-2 w-full no-wrap"):
                        ref_embed_a = ui.select(
                            options=ref_embed_options["value"],
                            value=speaker_condition_values["ref_embed_a"],
                            label="モデルA",
                        ).props("outlined dense options-dense").classes("flex-grow")
                        ref_embed_a_holder["value"] = ref_embed_a # type: ignore
                        ref_embed_a.on_value_change(on_ref_embed_change)
                        ref_embed_a.on_value_change(
                            lambda e: speaker_condition_values.__setitem__(
                                "ref_embed_a",
                                None if e.value == REF_EMBED_RELOAD else e.value,
                            )
                        )

                        ratio_a_label = ui.label().classes("w-8 text-right")
                        ratio_slider = ui.slider(
                            min=0,
                            max=1,
                            step=0.05,
                            value=speaker_condition_values["ratio_a"],
                        ).classes("w-56").props('track-color="orange" color="green" thumb-color="blue"')
                        ref_embed_ratio_holder["value"] = ratio_slider # type: ignore
                        ratio_b_label = ui.label().classes("w-8")
                        ratio_a_label.bind_text_from(
                            ratio_slider, "value", lambda v: f"{float(v):.2g}"
                        )
                        ratio_b_label.bind_text_from(
                            ratio_slider, "value", lambda v: f"{1.0 - float(v):.2g}"
                        )
                        ratio_slider.on_value_change(
                            lambda e: speaker_condition_values.__setitem__(
                                "ratio_a", float(e.value) # type: ignore
                            )
                        )

                        ref_embed_b = ui.select(
                            options=ref_embed_options["value"],
                            value=speaker_condition_values["ref_embed_b"],
                            label="モデルB",
                        ).props("outlined dense options-dense").classes("flex-grow")
                        ref_embed_b_holder["value"] = ref_embed_b # type: ignore
                        ref_embed_b.on_value_change(on_ref_embed_change)
                        ref_embed_b.on_value_change(
                            lambda e: speaker_condition_values.__setitem__(
                                "ref_embed_b",
                                None if e.value == REF_EMBED_RELOAD else e.value,
                            )
                        )
                    with ui.row().classes("items-center gap-2 w-full no-wrap"):
                        ui.label("混合方法: ")
                        method_toggle = ui.toggle(
                            {"linear": "linear", "slerp": "slerp"},
                            value=speaker_condition_values["method"],
                        ).props("")
                        ref_embed_method_holder["value"] = method_toggle # type: ignore
                        method_toggle.on_value_change(
                            lambda e: speaker_condition_values.__setitem__("method", e.value)
                        )
                    return

            async def on_voice_change(e):
                voice_select = voice_select_holder["value"]
                if voice_select is None:
                    return
                values: list = e.value if isinstance(e.value, list) else []
                if VOICE_RELOAD in values:
                    voice_select.set_value([])
                    loop = asyncio.get_event_loop()
                    voice_options["value"] = await loop.run_in_executor(None, list_server_voices)
                    speaker_condition_view.refresh()
                    return
                speaker_condition_values["voices"] = values

            voice_select = ui.select(
                options=voice_options["value"],
                value=speaker_condition_values["voices"],
                label="voice",
                multiple=True,
            ).props("outlined dense options-dense use-chips").classes("w-full")
            voice_select_holder["value"] = voice_select # type: ignore
            voice_select.on_value_change(on_voice_change)

        def on_mixed_ref_change(e):
            mixed_ref_enabled["value"] = bool(e.value)
            speaker_condition_view.refresh()

        mixed_ref_checkbox = ui.checkbox("混合 Speaker Inversion", on_change=on_mixed_ref_change)
        speaker_condition_view()

        async def _initial_voice_options_load():
            loop = asyncio.get_event_loop()
            voice_options["value"] = await loop.run_in_executor(None, list_server_voices)
            ref_embed_options["value"] = await loop.run_in_executor(
                None, list_speaker_embeddings
            )
            speaker_condition_view.refresh()
        ui.timer(0, _initial_voice_options_load, once=True)

        @ui.refreshable
        def cfg_scale_view():
            nonlocal cfg_scale_text_slider, cfg_scale_speaker_slider
            with ui.row().classes("items-center gap-4 w-full"):
                with ui.column().classes("gap-1"):
                    with ui.row().classes("items-center gap-1"):
                        ui.label("cfg_scale_text").classes("text-base")
                        ui.button(icon="restart_alt").props("flat dense round size=sm color=grey").on_click(lambda: cfg_scale_text_slider.set_value(3.0))
                    with ui.row().classes("items-center gap-2"):
                        cfg_scale_text_slider = ui.slider(
                            min=0, max=10, step=0.1, value=cfg_scale_values["text"]
                        ).props("label").classes("w-56")
                        cfg_scale_text_slider.on_value_change(
                            lambda e: cfg_scale_values.__setitem__("text", float(e.value))
                        )
                        ui.label().bind_text_from(cfg_scale_text_slider, "value", lambda v: f"{v:.1f}")
                with ui.column().classes("gap-1"):
                    with ui.row().classes("items-center gap-1"):
                        ui.label("cfg_scale_speaker").classes("text-base")
                        ui.button(icon="restart_alt").props("flat dense round size=sm color=grey").on_click(lambda: cfg_scale_speaker_slider.set_value(5.0))
                    with ui.row().classes("items-center gap-2"):
                        cfg_scale_speaker_slider = ui.slider(
                            min=0, max=10, step=0.1, value=cfg_scale_values["speaker"]
                        ).props("label").classes("w-56")
                        cfg_scale_speaker_slider.on_value_change(
                            lambda e: cfg_scale_values.__setitem__("speaker", float(e.value))
                        )
                        ui.label().bind_text_from(cfg_scale_speaker_slider, "value", lambda v: f"{v:.1f}")
                if server_model_state["voice_design"]:
                    with ui.column().classes("gap-1"):
                        with ui.row().classes("items-center gap-1"):
                            ui.label("cfg_scale_caption").classes("text-base")
                            ui.button(icon="restart_alt").props(
                                "flat dense round size=sm color=grey"
                            ).on_click(lambda: cfg_scale_caption_slider.set_value(3.0))
                        with ui.row().classes("items-center gap-2"):
                            cfg_scale_caption_slider = ui.slider(
                                min=0,
                                max=10,
                                step=0.1,
                                value=cfg_scale_caption_value["value"],
                            ).props("label").classes("w-56")
                            cfg_scale_caption_slider.on_value_change(
                                lambda e: cfg_scale_caption_value.__setitem__(
                                    "value", float(e.value)
                                )
                            )
                            ui.label().bind_text_from(
                                cfg_scale_caption_slider,
                                "value",
                                lambda v: f"{v:.1f}",
                            )

        cfg_scale_text_slider = None
        cfg_scale_speaker_slider = None
        cfg_scale_caption_slider = None
        cfg_scale_view()

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
                    ui.button("キューをクリア", on_click=clear_queue).props("dense").set_enabled(queue.qsize() > 0)
                    ui.label(f"待機中: {queue.qsize()} 件")
                    if current:
                        ui.label(f"処理中: {current.out_path.name}")
                    else:
                        ui.label("処理中: なし")

    # ═══════════════════════════════════════════════════════════════════════════════
    # 生成結果
    # ═══════════════════════════════════════════════════════════════════════════════
    with ui.expansion("生成結果", value=True).classes(
        "rounded-borders brdr overflow-hidden w-full"
    ).props('header-class="bg-grey-2 text-black"')as infer_expansion:
        with ui.column().classes("w-full gap-2"):
            queue_status()
            plyr_alt_control(result_control)
            result_list_holder["value"] = ui.column().classes("w-full gap-2")
