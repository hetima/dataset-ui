import time
from nicegui import ui

from testpage.testpage_ctx import TestCtx
from common.cpu_task_dialog import CpuTaskDialog
from common.model_cache import model_cache


def _dummy_task(_, queue, stop_event):
    """10秒かかるダミータスク"""
    total = 10
    queue.put({"type": "progress", "value": 0, "max": total})
    for i in range(total):
        if stop_event.is_set():
            return None
        time.sleep(1)
        queue.put({"type": "log", "text": f"ステップ {i + 1}/{total} 完了"})
        queue.put({"type": "progress", "value": i + 1})
    return {"done": True}


def tab_main(ctx: TestCtx):

    # ═══════════════════════════════════════════════════════════════════════════════
    # CpuTaskDialog テスト
    # ═══════════════════════════════════════════════════════════════════════════════

    def open_task():
        dlg = CpuTaskDialog(
            fn=_dummy_task,
            data=None,
            title="CpuTaskDialog テスト（10秒処理）",
            finish_callback=lambda ok, result: ui.notify(f"完了: {result}" if ok else "キャンセル"),
        )
        dlg.open()

    ui.button("CpuTaskDialog テスト", on_click=open_task)

    # ═══════════════════════════════════════════════════════════════════════════════
    # ModelCache テスト
    # ═══════════════════════════════════════════════════════════════════════════════

    _counter = {"n": 0}

    def add_dummy_cache():
        _counter["n"] += 1
        name = f"DummyModel-{_counter['n']}"
        model_cache.model_loaded(
            name=name,
            value=object(),
            get_func=lambda: None,
            dispose_func=lambda _: None,
        )
        ui.notify(f"キャッシュ登録: {name}", type="positive")

    ui.button("ダミーキャッシュ追加", icon="add", on_click=add_dummy_cache)

    # ═══════════════════════════════════════════════════════════════════════════════
    # ファイル一覧
    # ═══════════════════════════════════════════════════════════════════════════════

    ctx.table = ui.table(
        columns=[
            {"label": "Name", "field": "name", "name": "name", "align": "left"},
        ],
        rows=[],
        selection="multiple",
        row_key="name",
    ).classes("h-120 w-full no-shadow brdr q-pa-none")
