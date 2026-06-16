"""textarea に絵文字コンボボックスを取り付ける NiceGUI ラッパーです。"""

from __future__ import annotations

import json
from pathlib import Path

from nicegui import app, ui

ASSET_ROUTE = "/emoji-picker"
ASSET_DIR = Path(__file__).resolve().parent.parent / "publish" / "emoji-picker"

_assets_registered = False
_head_registered = False


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _ensure_assets() -> None:
    global _assets_registered, _head_registered
    if not _assets_registered:
        app.add_static_files(ASSET_ROUTE, ASSET_DIR)
        _assets_registered = True
    if not _head_registered:
        ui.add_head_html(f'<script src="{ASSET_ROUTE}/emoji-picker.js"></script>', shared=True)
        _head_registered = True


def attach_emoji_picker(textarea_el: ui.textarea, emoji_json_path: Path) -> None:
    """textarea に絵文字コンボボックスを取り付けます。"""
    _ensure_assets()

    emoji_data = json.loads(emoji_json_path.read_text(encoding="utf-8"))
    ta_id = f"c{textarea_el.id}"

    script = f"""
    (() => {{
      const attach = () => {{
        const el = document.getElementById({_json(ta_id)});
        const ta = el?.tagName === 'TEXTAREA' ? el : el?.querySelector('textarea');
        if (!ta || !window.EmojiPicker) {{ setTimeout(attach, 30); return; }}
        window.EmojiPicker.attach(ta, {_json(emoji_data)});
      }};
      attach();
    }})();
    """

    client = ui.context.client
    client.on_connect(lambda: ui.run_javascript(script))
    ui.timer(0.1, lambda: ui.run_javascript(script), once=True)
