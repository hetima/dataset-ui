
from pathlib import Path
from nicegui import ui, app
from edit.edit_app_ctx import EditCtx
from common.wavesurfer import MultitrackWidget

# JS→Python へ境界更新を通知するカスタムイベント名
_REGION_EVENT = "compi-region-updated"
# JS側グローバルコールバック関数名
_REGION_CB = "editCompiRegionUpdated"


def tab_compi(ctx: EditCtx):
    mt = MultitrackWidget("editCompiMultitrack", min_px_per_sec=10)

        # トラックインデックス→Region リスト [{start, end}, ...] を保持
    track_regions: list[list[dict]] = []

    def on_region_updated(e):
        """JS から region 変化イベントを受け取る。e.args = [trackIdx, [{start, end}, ...]]"""
        args = e.args
        if not isinstance(args, list) or len(args) < 2:
            return
        idx = int(args[0])
        regions = [{"start": round(r["start"], 3), "end": round(r["end"], 3)} for r in (args[1] or [])]
        while len(track_regions) <= idx:
            track_regions.append([])
        track_regions[idx] = regions

    # カスタムイベントをページレベルで受信
    ui.on(_REGION_EVENT, on_region_updated)

    # JS グローバル関数を定義：region 変化時にページへイベントを送信する
    ui.add_body_html(f'''
<script>
function {_REGION_CB}(trackIdx, regions) {{
    emitEvent("{_REGION_EVENT}", [trackIdx, regions]);
}}
</script>
''')

    with ui.column().classes("w-full gap-2"):
        # 操作バー
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="play_arrow").props("flat dense").on(
                "click", js_handler=mt.play_js()
            )
            ui.button(icon="stop").props("flat dense").on(
                "click", js_handler=mt.pause_js()
            )
            ui.button(icon="fast_rewind").props("flat dense").on(
                "click", js_handler=mt.seek_js(-10)
            )
            ui.button(icon="fast_forward").props("flat dense").on(
                "click", js_handler=mt.seek_js(10)
            )
            ui.separator().props("vertical")
            ui.icon("volume_up").style("font-size: 1.2em; color: #666")
            ui.slider(min=0, max=1, step=0.05, value=1).style("width: 120px").on(
                "update:model-value",
                js_handler=mt.volume_js(),
            )
            ui.separator().props("vertical")
            ui.label("Zoom:")
            ui.slider(min=10, max=200, step=10, value=10).style("width: 160px").on(
                "update:model-value",
                js_handler=mt.zoom_js(),
            )
            ui.separator().props("vertical")
            ui.switch("イベントロック").on(
                "update:model-value",
                lambda e: mt.set_locked(e.args),
            )
            ui.separator().props("vertical")
            ui.button("読み込む", icon="refresh", on_click=lambda: _load(ctx, mt)).props("flat dense")

        # Multitrack コンテナ
        mt.build()

    # スペースキーで再生/停止（INPUT/TEXTAREA 以外では常に横取り）
    ui.add_body_html(f'''
<script>
document.addEventListener("keydown", (e) => {{
    if (e.key !== " ") return;
    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const m = window["editCompiMultitrack"];
    if (m) m.isPlaying() ? m.pause() : m.play();
}}, true);
</script>
''')


def _load(ctx: EditCtx, mt: MultitrackWidget):
    """選択中ファイルをMultitrackのトラックとしてロードする。"""
    files = ctx.target_files()
    if not files:
        ui.notify("ファイルが選択されていません", type="warning")
        return

    tracks = []
    for i, f in enumerate(files):
        path = f["path"] if hasattr(f, "__getitem__") else f.path
        p = Path(path)
        mount = "/" + p.parent.name
        app.add_media_files(mount, str(p.parent))
        url = f"{mount}/{p.name}"
        tracks.append({
            "id": i,
            "name": p.name,
            "url": url,
            "startPosition": 0,
            "draggable": True,
            "options": {
                "waveColor": _track_color(i, "wave"),
                "progressColor": _track_color(i, "progress"),
            },
        })

    mt.load_tracks(tracks, region_callback=_REGION_CB)


_COLORS = [
    ("hsl(200, 80%, 55%)", "hsl(200, 80%, 25%)"),
    ("hsl(46, 87%, 49%)",  "hsl(46, 87%, 20%)"),
    ("hsl(161, 87%, 49%)", "hsl(161, 87%, 20%)"),
    ("hsl(300, 70%, 55%)", "hsl(300, 70%, 25%)"),
    ("hsl(25, 87%, 49%)",  "hsl(25, 87%, 20%)"),
]


def _track_color(index: int, kind: str) -> str:
    wave, progress = _COLORS[index % len(_COLORS)]
    return wave if kind == "wave" else progress
