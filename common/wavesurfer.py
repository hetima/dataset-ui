from pathlib import Path
from types import SimpleNamespace
from nicegui import ui, app


_WAVESURFER_CDN = "https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.esm.js"
_REGIONS_CDN = "https://unpkg.com/wavesurfer.js@7/dist/plugins/regions.esm.js"
_MULTITRACK_CDN = "/static/multitrack.min.js"


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
    """Multitrack と RegionsPlugin を事前ロード。main_page 先頭で一度だけ呼ぶ。"""
    app.add_static_files("/static", str(Path(__file__).parent.parent / "static"))
    ui.add_head_html(f'<script src="{_MULTITRACK_CDN}"></script>')
    ui.add_head_html(f'''
<script type="module">
    import("{_REGIONS_CDN}").then(m => {{ window.WaveSurferRegions = m.default; }});
</script>
''')


class MultitrackWidget:
    """wavesurfer-multitrack のラッパー。複数ファイルをタイムライン上に並べて再生・編集できる。"""

    def __init__(self, instance_name: str, min_px_per_sec: int = 10):
        self._name = instance_name
        self._min_px_per_sec = min_px_per_sec
        self._el: ui.element | None = None
        self._tracks: list[dict] = []
        self._region_callback: str = ""
        self._locked = False

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

    def load_tracks(self, tracks: list[dict], region_callback: str = "") -> None:
        """トラックリストをセットして再描画する。
        region_callback: region 変化時に呼ぶ JS 関数名（省略可）。
            関数シグネチャ: (trackIndex, regions: [{start, end}][]) を受け取る。
        """
        self._tracks = tracks
        if region_callback:
            self._region_callback = region_callback
        cb = self._region_callback
        name = self._name
        import json
        tracks_json = json.dumps(tracks)
        el_id = f"c{self._el.id}" if self._el else ""
        locked_js = "true" if self._locked else "false"
        # region変化をPythonに通知するJS（region_callbackが空なら何もしない）
        notify_cb = f"{cb}(trackIdx, rp.getRegions().map(r => ({{start: r.start, end: r.end}})));" if cb else ""
        ui.run_javascript(f'''
            (() => {{
                const tryLoad = () => {{
                    if (!window["{name}"]) {{ setTimeout(tryLoad, 100); return; }}
                    window["{name}"].destroy();
                    window["{name}"] = null;
                    const el = document.getElementById("{el_id}");
                    if (!el) return;
                    const mt = Multitrack.create({tracks_json}, {{
                        container: el,
                        minPxPerSec: {self._min_px_per_sec},
                        cursorWidth: 2,
                        cursorColor: "#D72F21",
                        trackBackground: "#2D2D2D",
                        trackBorderColor: "#7C7C7C",
                        dragBounds: false,
                    }});
                    window["{name}"] = mt;
                    mt.setLocked({locked_js});

                    // canplay後に各トラックへ RegionsPlugin を追加登録
                    mt.once("canplay", () => {{
                        const wsList = mt.wavesurfers;
                        if (!wsList || !window.WaveSurferRegions) return;

                        // 全トラックの RegionsPlugin を配列で保持（排他制御に使う）
                        const allRp = [];
                        // enableDragSelection の解除関数（ロック切り替え用）
                        const dragDisposers = [];

                        wsList.forEach((ws, trackIdx) => {{
                            if (!ws) {{ allRp.push(null); dragDisposers.push(null); return; }}
                            const rp = ws.registerPlugin(window.WaveSurferRegions.create());
                            allRp.push(rp);

                            // ドラッグ選択を有効化し、解除関数を保持
                            const disposeDrag = rp.enableDragSelection({{ color: "rgba(100, 200, 255, 0.25)" }});
                            dragDisposers.push(disposeDrag || null);

                            // 他トラックの重複 Region を境界に合わせて縮小・削除する
                            const onRegionChange = (changedRegion) => {{
                                allRp.forEach((otherRp, otherIdx) => {{
                                    if (otherIdx === trackIdx || !otherRp) return;
                                    otherRp.getRegions().forEach(r => {{
                                        const overlaps = r.start < changedRegion.end && r.end > changedRegion.start;
                                        if (!overlaps) return;
                                        const fullyContained = r.start >= changedRegion.start && r.end <= changedRegion.end;
                                        if (fullyContained) {{
                                            r.remove();
                                        }} else if (r.start < changedRegion.start && r.end <= changedRegion.end) {{
                                            // 右側が重なる → end を縮める
                                            r.setOptions({{ end: changedRegion.start }});
                                        }} else if (r.start >= changedRegion.start && r.end > changedRegion.end) {{
                                            // 左側が重なる → start を縮める
                                            r.setOptions({{ start: changedRegion.end }});
                                        }} else {{
                                            // 既存 Region が新 Region を完全包含 → 新 Region の右側を残して分割は難しいので削除
                                            r.remove();
                                        }}
                                    }});
                                }});
                                {notify_cb}
                            }};

                            rp.on("region-created", onRegionChange);
                            rp.on("region-updated", onRegionChange);

                            // 下半分クリックで Region を分割。上半分クリックは移動・リサイズ操作用に残す。
                            rp.on("region-clicked", (r, e) => {{
                                e.stopPropagation();
                                const regionRect = r.element.getBoundingClientRect();
                                const isLowerHalf = e.clientY - regionRect.top >= regionRect.height / 2;
                                if (!isLowerHalf || mt.locked) return;

                                const wrapper = ws.getWrapper();
                                const rect = wrapper.getBoundingClientRect();
                                const duration = ws.getDuration();
                                const splitAt = ((e.clientX - rect.left) / rect.width) * duration;
                                const minLength = 0.01;
                                if (splitAt > r.start + minLength && splitAt < r.end - minLength) {{
                                    const color = r.color || "rgba(100, 200, 255, 0.25)";
                                    const left = {{ start: r.start, end: splitAt, color }};
                                    const right = {{ start: splitAt, end: r.end, color }};
                                    r.remove();
                                    rp.addRegion(left);
                                    rp.addRegion(right);
                                    {notify_cb}
                                }}
                            }});
                        }});

                        // グローバルに保持（ロック切り替え用）
                        window["{name}__rp"] = allRp;
                        window["{name}__dragDisposers"] = dragDisposers;
                        mt.setLocked({locked_js});
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
        """イベントロックを切り替える。Region 作成は許可し、トラック移動だけを禁止する。"""
        self._locked = locked
        name = self._name
        locked_js = "true" if locked else "false"
        ui.run_javascript(f'''
            (() => {{
                const mt = window["{name}"];
                if (!mt) return;
                mt.setLocked({locked_js});
            }})();
        ''')

    def volume_js(self) -> str:
        """マスターボリュームスライダーの update:model-value ハンドラ。トラック別音量は変更しない。"""
        name = self._name
        return (
            f"(v) => {{ const m = window['{name}']; if (!m) return;"
            f" if (typeof m.setMasterVolume === 'function') m.setMasterVolume(v); }}"
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
