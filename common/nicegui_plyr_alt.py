"""NiceGUI で PlyrAlt を使うための薄いラッパーです。"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from uuid import uuid4

from nicegui import app, ui


ASSET_ROUTE = "/plyr-alt"
ASSET_DIR = Path(__file__).resolve().parent.parent / "publish" / "plyr-alt"
_assets_registered = False
_head_registered = False


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def ensure_plyr_alt_assets() -> None:
    """PlyrAlt の JS/CSS を NiceGUI に一度だけ登録します。"""
    global _assets_registered, _head_registered

    if not _assets_registered:
        app.add_static_files(ASSET_ROUTE, ASSET_DIR)
        _assets_registered = True

    if not _head_registered:
        ui.add_head_html(f'<link rel="stylesheet" href="{ASSET_ROUTE}/plyr-alt.css">', shared=True)
        ui.add_head_html(f'<script src="{ASSET_ROUTE}/plyr-alt.js"></script>', shared=True)
        _head_registered = True


def _load_assets_script() -> str:
    """head 読み込みが間に合わない場合にも JS/CSS を読み込む JavaScript を返します。"""
    return f"""
    if (!document.querySelector('link[data-plyr-alt-css]')) {{
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = {_json(f"{ASSET_ROUTE}/plyr-alt.css")};
      link.dataset.plyrAltCss = 'true';
      document.head.appendChild(link);
    }}
    if (!window.PlyrAlt && !document.querySelector('script[data-plyr-alt-js]')) {{
      const script = document.createElement('script');
      script.src = {_json(f"{ASSET_ROUTE}/plyr-alt.js")};
      script.dataset.plyrAltJs = 'true';
      document.head.appendChild(script);
    }}
    """


def _init_when_ready(script: str) -> str:
    """JS アセット読み込み完了後に初期化処理を実行する JavaScript を返します。"""
    return f"""
    (() => {{
      {_load_assets_script()}
      const init = () => {{
        if (!window.PlyrAlt || !window.PlyrAltControl) {{
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
class PlyrAltControl:
    """同一ページ内の PlyrAlt をまとめて管理する共有コントローラーです。"""

    id: str = field(default_factory=lambda: f"plyr_alt_control_{uuid4().hex}")
    volume: float = 1.0

    def render(self):
        """共有ボリューム UI を描画します。"""
        ensure_plyr_alt_assets()
        element_id = f"{self.id}_element"
        options = _json({"id": self.id, "volume": self.volume})
        element = ui.html(f'<div id="{element_id}"></div>')
        _run_when_client_connects(
            _init_when_ready(
                f"const el = document.getElementById({_json(element_id)});"
                f"if (!el) return window.setTimeout(init, 20);"
                f"window.PlyrAltControl.get({_json(self.id)}, {options}).mount(el);"
            )
        )
        return element


@dataclass
class PlyrAltElement:
    """NiceGUI 側から後で削除できる PlyrAlt のハンドルです。"""

    id: str
    element: object

    def delete(self) -> None:
        """JS インスタンスを破棄してから NiceGUI 要素を削除します。"""
        ui.run_javascript(f"window.PlyrAlt && window.PlyrAlt.destroy({_json(self.id)});")
        self.element.delete() # type: ignore

    def __getattr__(self, name: str):
        return getattr(self.element, name)


def plyr_alt_control(control: PlyrAltControl | None = None):
    """PlyrAltControl の共有ボリューム UI を描画します。"""
    control = control or PlyrAltControl()
    return control.render()


def plyr_alt(
    src: str,
    label: str = "",
    *,
    control: PlyrAltControl | str | None = None,
    height: int = 96,
    colors: dict[str, str] | None = None,
):
    """波形表示付き audio プレイヤーを NiceGUI に描画します。"""
    ensure_plyr_alt_assets()
    element_id = f"plyr_alt_{uuid4().hex}"
    control_id = control.id if isinstance(control, PlyrAltControl) else (control or "default")
    options = {
        "id": element_id,
        "src": src,
        "label": label,
        "control": control_id,
        "height": height,
    }

    if colors:
        options["colors"] = colors

    element = ui.html(f'<div id="{element_id}" style="width:600px;"></div>')
    _run_when_client_connects(
        _init_when_ready(
            f"const el = document.getElementById({_json(element_id)});"
            f"if (!el) return window.setTimeout(init, 20);"
            f"if (!window.PlyrAlt.get({_json(element_id)})) "
            f"new window.PlyrAlt(el, {_json(options)});"
        )
    )
    return PlyrAltElement(id=element_id, element=element)
