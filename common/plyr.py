from pathlib import Path
from types import SimpleNamespace
from nicegui import ui, app

_PLYR_DIST = Path(__file__).parent.parent / "publish" / "plyr"
if _PLYR_DIST.exists():
    app.add_static_files("/plyr", str(_PLYR_DIST))


class PlyrWidget:
    """plyr.js を使ったオーディオプレイヤー。波形描画なしで軽量。"""

    def __init__(self, instance_name: str, autoplay: bool = False):
        self._name = instance_name
        self._autoplay = autoplay
        self._audio_el: ui.element | None = None
        self._name_label: ui.label | None = None

    def build(self) -> "PlyrWidget":
        """audio 要素を現在のコンテキストに配置し、plyr で初期化する。"""
        ui.add_head_html('<link rel="stylesheet" href="/plyr/plyr.css">', shared=True)
        ui.add_head_html('<script src="/plyr/plyr.min.js"></script>', shared=True)
        self._audio_el = ui.element("audio").props('preload="none"')
        name = self._name
        _audio_el_id = self._audio_el.id
        autoplay_js = "p.play();" if self._autoplay else ""
        ui.context.client.on_connect(lambda: ui.run_javascript(f"""
            (function init() {{
                if (typeof Plyr === 'undefined') {{ setTimeout(init, 100); return; }}
                const el = document.getElementById("c{_audio_el_id}")
                if (!el) {{ setTimeout(init, 100); return; }}
                if (window["{name}"]) return;
                window["{name}"] = new Plyr(el, {{
                    controls: ["play", "progress", "current-time", "duration", "mute", "volume"],
                    invertTime: false,
                    resetOnEnd: true,
                }});
            }})();
        """))
        return self

    def name_label(self) -> ui.label:
        """ファイル名表示用ラベルを生成して返す。load()時に自動更新される。"""
        self._name_label = ui.label("")
        return self._name_label

    def load(self, path: str):
        """音声ファイルをロードして再生する。ファイルシステムのパスを渡す。"""
        p = Path(path)
        if self._name_label:
            self._name_label.set_text(p.name)
        mount = "/" + p.parent.name
        app.add_media_files(mount, str(p.parent))
        url = f"{mount}/{p.name}"
        name = self._name
        autoplay = "true" if self._autoplay else "false"
        ui.run_javascript(f"""
            const name = "{name}";
            const url = {url!r};
            if (window[name]) {{
                window[name].source = {{ type: "audio", sources: [{{ src: url }}], autoplay: {autoplay} }};
            }}
        """)


def simple_plyr_player(
    name: str,
    visible: bool = True,
    autoplay: bool = False,
) -> SimpleNamespace:
    """plyrプレイヤーを生成する。result.ws / result.container で参照できる（wsはPlyrWidget）。"""
    pw = PlyrWidget(name, autoplay)
    with ui.column().classes("items-start gap-0").set_visibility(visible) as container:
        pw.name_label().style("font-size: 0.85em; color: #666; margin-bottom: 2px;")
        pw.build()
    return SimpleNamespace(plyr=pw, container=container)
