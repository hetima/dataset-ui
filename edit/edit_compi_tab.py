
from pathlib import Path
from nicegui import ui, app
from edit.edit_app_ctx import EditCtx
from common.wavesurfer import MultitrackWidget


def tab_compi(ctx: EditCtx):
    mt = MultitrackWidget("editCompiMultitrack", min_px_per_sec=10)

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
            "url": url,
            "startPosition": 0,
            "draggable": True,
            "options": {
                "waveColor": _track_color(i, "wave"),
                "progressColor": _track_color(i, "progress"),
            },
        })

    mt.load_tracks(tracks)


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
