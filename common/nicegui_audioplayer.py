"""NiceGUI で AudioPlayer を使うための薄いラッパーです。"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from nicegui import app, ui


ASSET_ROUTE = "/audioplayer"
ASSET_DIR = Path(__file__).resolve().parent.parent / "publish" / "audioplayer"
_assets_registered = False
_head_registered = False


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def ensure_audioplayer_assets() -> None:
    """AudioPlayer の JS/CSS を NiceGUI に一度だけ登録します。"""
    global _assets_registered, _head_registered

    if not _assets_registered:
        app.add_static_files(ASSET_ROUTE, ASSET_DIR)
        _assets_registered = True

    if not _head_registered:
        ui.add_head_html(f'<link rel="stylesheet" href="{ASSET_ROUTE}/audioplayer.css">', shared=True)
        ui.add_head_html(f'<script src="{ASSET_ROUTE}/audioplayer.js"></script>', shared=True)
        _head_registered = True


def _load_assets_script() -> str:
    """head 読み込みが間に合わない場合にも JS/CSS を読み込む JavaScript を返します。"""
    return f"""
    if (!document.querySelector('link[data-audioplayer-css]')) {{
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = {_json(f"{ASSET_ROUTE}/audioplayer.css")};
      link.dataset.audioplayerCss = 'true';
      document.head.appendChild(link);
    }}
    if (!window.AudioPlayer && !document.querySelector('script[data-audioplayer-js]')) {{
      const script = document.createElement('script');
      script.src = {_json(f"{ASSET_ROUTE}/audioplayer.js")};
      script.dataset.audioplayerJs = 'true';
      document.head.appendChild(script);
    }}
    """


def _init_when_ready(script: str) -> str:
    """JS アセット読み込み完了後に初期化処理を実行する JavaScript を返します。"""
    return f"""
    (() => {{
      {_load_assets_script()}
      const init = () => {{
        if (!window.AudioPlayer || !window.AudioPlayerControl) {{
          window.setTimeout(init, 20);
          return;
        }}
        {script}
      }};
      init();
    }})();
    """


def _run_when_client_connects(script: str) -> None:
    """初回描画時にも後からの追加時にも初期化 JS を実行します。"""
    client = ui.context.client
    client.on_connect(lambda: ui.run_javascript(script))
    ui.timer(0.1, lambda: ui.run_javascript(script), once=True)


@dataclass
class AudioPlayerControl:
    """UI なし軽量コントローラー。同時再生を防ぐための管理のみ行います。"""

    id: str = field(default_factory=lambda: f"audio_player_control_{uuid4().hex}")


class AudioPlayerWidget:
    """シンプルな横一列オーディオプレイヤー。PlyrWidget の代替として使用できます。"""

    def __init__(
        self,
        instance_name: str,
        autoplay: bool = False,
        control: AudioPlayerControl | str | None = None,
    ) -> None:
        self._name = instance_name
        self._autoplay = autoplay
        self._control = control
        self._name_label: ui.label | None = None

    def build(self) -> "AudioPlayerWidget":
        """プレイヤー UI を現在の NiceGUI コンテキストに配置します。"""
        ensure_audioplayer_assets()
        element_id = f"audioplayer_{self._name}"
        if isinstance(self._control, AudioPlayerControl):
            control_id = self._control.id
        elif isinstance(self._control, str):
            control_id = self._control
        else:
            control_id = "default"

        options = _json({
            "id": element_id,
            "name": self._name,
            "control": control_id,
            "autoplay": self._autoplay,
        })
        ui.html(f'<div id="{element_id}"></div>')
        _run_when_client_connects(
            _init_when_ready(
                f"const el = document.getElementById({_json(element_id)});"
                f"if (!el) return window.setTimeout(init, 20);"
                f"if (!window.AudioPlayer.get({_json(self._name)})) "
                f"new window.AudioPlayer(el, {options});"
            )
        )
        return self

    def name_label(self) -> ui.label:
        """ファイル名表示ラベルを生成して返します。load() 時に自動更新されます。"""
        self._name_label = ui.label("")
        return self._name_label

    def load(self, path: str) -> None:
        """音声ファイルをロードします。ファイルシステムのパスを渡してください。"""
        p = Path(path)
        if self._name_label is not None:
            self._name_label.set_text(p.name)
        mount = "/" + p.parent.name
        app.add_media_files(mount, str(p.parent))
        url = f"{mount}/{p.name}"
        autoplay = "true" if self._autoplay else "false"
        ui.run_javascript(
            f"const _ap = window.AudioPlayer && window.AudioPlayer.get({_json(self._name)});"
            f"if (_ap) _ap.load({_json(url)}, {autoplay});"
        )


def simple_audio_player(
    name: str,
    visible: bool = True,
    autoplay: bool = False,
    control: AudioPlayerControl | None = None,
) -> SimpleNamespace:
    """
    AudioPlayerWidget を生成するヘルパー関数。

    戻り値: SimpleNamespace(player=AudioPlayerWidget, container=ui.column)
    """
    widget = AudioPlayerWidget(name, autoplay=autoplay, control=control)
    with ui.column().classes("items-start gap-0").set_visibility(visible) as container:
        widget.name_label().style("font-size: 0.85em; color: #666; margin-bottom: 2px;")
        widget.build()
    return SimpleNamespace(player=widget, container=container)
