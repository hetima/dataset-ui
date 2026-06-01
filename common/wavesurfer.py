from pathlib import Path
from types import SimpleNamespace
from nicegui import ui, app


_WAVESURFER_CDN = "https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.esm.js"
_MULTITRACK_CDN = "https://unpkg.com/wavesurfer-multitrack/dist/multitrack.min.js"


def setup_wavesurfer():
    """WaveSurferをwindow.WaveSurferとして事前ロード。main_page先頭で一度だけ呼ぶ。"""
    ui.add_head_html(f'''
<script type="module">
    import("{_WAVESURFER_CDN}").then(m => {{ window.WaveSurfer = m.default; }});
</script>
''')


class WaveSurferWidget:
    """WaveSurferのラッパー。build()でDIVを生成し、タブ非表示でも自動初期化する。"""

    def __init__(self, instance_name: str, width: str = "500px", height: int = 60,
                 wave_color: str = "#4F4A85", progress_color: str = "#A48CE4",
                 autoplay: bool = False):
        self._name = instance_name
        self._width = width
        self._height = height
        self._wave_color = wave_color
        self._progress_color = progress_color
        self._autoplay = autoplay
        self._el: ui.element | None = None
        self._duration_label: ui.label | None = None
        self._name_label: ui.label | None = None

    def build(self) -> "WaveSurferWidget":
        """波形表示用DIVを現在のNiceGUIコンテキストに配置し、初期化をスケジュールする。"""
        self._el = ui.element("div").style(f"width: {self._width}; display: block; margin: 0; padding: 0; line-height: 0;")
        ui.context.client.on_connect(self._init)
        return self

    def name_label(self, **kwargs) -> ui.label:
        """ファイル名表示用ラベルを生成して返す。load()時に自動更新される。"""
        self._name_label = ui.label("").style(**kwargs)
        return self._name_label

    def duration_label(self, **kwargs) -> ui.label:
        """duration表示用ラベルを生成して返す。build()の後に呼ぶ。"""
        self._duration_label = ui.label("(--:--)").style("font-family: monospace;", **kwargs)
        return self._duration_label

    async def _init(self):
        el_id = f"c{self._el.id}" # type: ignore
        name = self._name
        dur_id = f"c{self._duration_label.id}" if self._duration_label else ""
        await ui.run_javascript(f'''
            const tryCreate = () => {{
                if (!window.WaveSurfer) {{ setTimeout(tryCreate, 100); return; }}
                const el = document.getElementById("{el_id}");
                if (!el) {{ setTimeout(tryCreate, 100); return; }}
                if (window["{name}"]) return;
                window["{name}"] = window.WaveSurfer.create({{
                    container: el,
                    waveColor: "{self._wave_color}",
                    progressColor: "{self._progress_color}",
                    height: {self._height},
                }});
                window["{name}"].on("error", (e) => console.error("[wavesurfer:{name}] error:", e));
                window["{name}"].on("ready", () => {{
                    window["{name}"].seekTo(0);
                    {'window["' + name + '"].play();' if self._autoplay else ''}
                    const dur = window["{name}"].getDuration();
                    const m = Math.floor(dur / 60);
                    const s = String(Math.floor(dur % 60)).padStart(2, "0");
                    const el = document.getElementById("{dur_id}");
                    if (el) el.textContent = `(${{m}}:${{s}})`;
                }});
            }};
            tryCreate();
        ''')

    def play_js(self) -> str:
        """playを呼ぶjs_handler文字列を返す。ui.buttonのjs_handlerに渡す。"""
        return f"() => window['{self._name}'] && window['{self._name}'].play()"

    def pause_js(self) -> str:
        """pauseを呼ぶjs_handler文字列を返す。ui.buttonのjs_handlerに渡す。"""
        return f"() => window['{self._name}'] && window['{self._name}'].pause()"

    def play_pause_js(self) -> str:
        """playPauseを呼ぶjs_handler文字列を返す。ui.buttonのjs_handlerに渡す。"""
        return f"() => window['{self._name}'] && window['{self._name}'].playPause()"

    def load(self, path: str):
        """音声ファイルをロードして再生する。ファイルシステムのパスを渡す。"""
        p = Path(path)
        if self._name_label:
            self._name_label.set_text(p.name)
        mount = "/" + p.parent.name
        app.add_media_files(mount, str(p.parent))
        url = f"{mount}/{p.name}"
        ui.run_javascript(f"window['{self._name}'] && window['{self._name}'].load({url!r})")


def setup_multitrack():
    """Multitrackをwindow.Multitrackとして事前ロード。main_page先頭で一度だけ呼ぶ。"""
    ui.add_head_html(f'<script src="{_MULTITRACK_CDN}"></script>')


class MultitrackWidget:
    """wavesurfer-multitrack のラッパー。複数ファイルをタイムライン上に並べて再生・編集できる。"""

    def __init__(self, instance_name: str, min_px_per_sec: int = 10):
        self._name = instance_name
        self._min_px_per_sec = min_px_per_sec
        self._el: ui.element | None = None
        self._tracks: list[dict] = []

    def build(self) -> "MultitrackWidget":
        """コンテナDIVを配置し、接続時に初期化をスケジュールする。"""
        self._el = ui.element("div").style("width: 100%; background: #2d2d2d;")
        ui.context.client.on_connect(self._init)
        return self

    async def _init(self):
        el_id = f"c{self._el.id}"  # type: ignore
        name = self._name
        min_px = self._min_px_per_sec
        await ui.run_javascript(f'''
            const tryCreate = () => {{
                if (typeof Multitrack === "undefined") {{ setTimeout(tryCreate, 100); return; }}
                const el = document.getElementById("{el_id}");
                if (!el) {{ setTimeout(tryCreate, 100); return; }}
                if (window["{name}"]) return;
                window["{name}"] = Multitrack.create([], {{
                    container: el,
                    minPxPerSec: {min_px},
                    cursorWidth: 2,
                    cursorColor: "#D72F21",
                    trackBackground: "#2D2D2D",
                    trackBorderColor: "#7C7C7C",
                    dragBounds: false,
                }});
            }};
            tryCreate();
        ''')

    def load_tracks(self, tracks: list[dict]):
        """トラックリストをセットして再描画する。各要素は {id, url, startPosition, ...} の dict。"""
        self._tracks = tracks
        name = self._name
        import json
        tracks_json = json.dumps(tracks)
        ui.run_javascript(f'''
            (async () => {{
                const tryLoad = () => {{
                    if (!window["{name}"]) {{ setTimeout(tryLoad, 100); return; }}
                    window["{name}"].destroy();
                    window["{name}"] = null;
                    const el = document.getElementById("c{self._el.id if self._el else ''}");
                    if (!el) return;
                    window["{name}"] = Multitrack.create({tracks_json}, {{
                        container: el,
                        minPxPerSec: {self._min_px_per_sec},
                        cursorWidth: 2,
                        cursorColor: "#D72F21",
                        trackBackground: "#2D2D2D",
                        trackBorderColor: "#7C7C7C",
                        dragBounds: false,
                    }});
                }};
                tryLoad();
            }})();
        ''')

    def play_js(self) -> str:
        return f"() => window['{self._name}'] && window['{self._name}'].play()"

    def pause_js(self) -> str:
        return f"() => window['{self._name}'] && window['{self._name}'].pause()"

    def play_pause_js(self) -> str:
        return f"() => {{ const m = window['{self._name}']; if (m) {{ m.isPlaying() ? m.pause() : m.play(); }} }}"

    def seek_js(self, seconds: float) -> str:
        return f"() => {{ const m = window['{self._name}']; if (m) m.setTime(m.getCurrentTime() + {seconds}); }}"

    def zoom_js(self) -> str:
        """zoom スライダーの update:model-value ハンドラ文字列を返す。"""
        return f"(v) => window['{self._name}'] && window['{self._name}'].zoom(v)"

    def set_locked(self, locked: bool):
        """ドラッグロックを切り替えて再構築する。load_tracks が一度も呼ばれていない場合は何もしない。"""
        if not self._tracks:
            return
        for t in self._tracks:
            t["draggable"] = not locked
        self.load_tracks(self._tracks)

    def volume_js(self) -> str:
        """マスターボリュームスライダーの update:model-value ハンドラ。全トラックに一括適用する。"""
        name = self._name
        return (
            f"(v) => {{ const m = window['{name}']; if (!m) return;"
            f" const ws = m.wavesurfers; if (ws) ws.forEach(w => w && w.setVolume(v)); }}"
        )


def simple_player(
    name: str,
    visible: bool = True,
    width: str = "500px",
    height: int = 60,
    wave_color: str = "#5375A1",
    progress_color: str = "#679DB5",
    autoplay: bool = False,
) -> SimpleNamespace:
    """WaveSurferプレイヤーを生成する。result.ws / result.container で参照できる。"""
    ws = WaveSurferWidget(name, width, height, wave_color, progress_color, autoplay)
    with ui.column().classes("items-start gap-0").set_visibility(visible) as container:
        ws.build()
        with ui.row().classes("items-center gap-0"):
            ui.button(icon="play_arrow").props("flat").on(
                "click", js_handler=ws.play_js()
            ).style("padding: 2px 4px;")
            ui.button(icon="pause").props("flat").on(
                "click", js_handler=ws.pause_js()
            ).style("padding: 2px 4px;")
            ws.name_label()
            ws.duration_label().style("margin:0 0 0 10px")
            ui.slider(min=0, max=1, step=0.05, value=1).style(
                "width: 120px; margin:0 0 0 20px"
            ).on(
                "update:model-value",
                js_handler=f"(v) => window['{ws._name}'] && window['{ws._name}'].setVolume(v)",
            )
    return SimpleNamespace(ws=ws, container=container)
