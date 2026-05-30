from pathlib import Path
from nicegui import ui, app


_WAVESURFER_CDN = "https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.esm.js"


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
                 wave_color: str = "#4F4A85", progress_color: str = "#A48CE4"):
        self._name = instance_name
        self._width = width
        self._height = height
        self._wave_color = wave_color
        self._progress_color = progress_color
        self._el: ui.element | None = None

    def build(self) -> "WaveSurferWidget":
        """波形表示用DIVを現在のNiceGUIコンテキストに配置し、初期化をスケジュールする。"""
        self._el = ui.element("div").style(f"width: {self._width}; display: block; margin: 0; padding: 0; line-height: 0;")
        ui.context.client.on_connect(self._init)
        return self

    async def _init(self):
        el_id = f"c{self._el.id}" # type: ignore
        name = self._name
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
            }};
            tryCreate();
        ''')

    def play_pause_js(self) -> str:
        """playPauseを呼ぶjs_handler文字列を返す。ui.buttonのjs_handlerに渡す。"""
        return f"() => window['{self._name}'] && window['{self._name}'].playPause()"

    def load(self, path: str):
        """音声ファイルをロードして再生する。ファイルシステムのパスを渡す。"""
        p = Path(path)
        mount = "/" + p.parent.name
        app.add_media_files(mount, str(p.parent))
        url = f"{mount}/{p.name}"
        ui.run_javascript(f"window['{self._name}'] && window['{self._name}'].load({url!r})")
