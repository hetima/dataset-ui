---
description: "NiceGUI framework patterns and conventions. Use when creating or modifying UI components, pages, dialogs, bindings, or background tasks in this NiceGUI project."
applyTo: "**/*.py"
---

# NiceGUI Conventions (dataset-ui)

## UI Context & Client Safety

**必須**: `@binding.bindable_dataclass` のCtxクラスでは初期化時に `self.client = ui.context.client` を保存し、非同期コールバック内でUI操作を行う際は `with self.client:` でラップする。

```python
@binding.bindable_dataclass
class MyCtx:
    def __init__(self, worker):
        self.client = ui.context.client  # 初期化時に保存

    def notify(self, text):
        with self.client:
            ui.notify(text)
```

`with self.client:` なしに非同期コンテキストから `ui.notify()` を呼ぶと `RuntimeError: no context` でクラッシュする。

## バインディング

| メソッド | 用途 |
|---------|------|
| `.bind_value(ctx, "field")` | 双方向バインディング |
| `.bind_value_from(obj, "field")` | 片方向（表示のみ） |
| `.bind_visibility_from(obj, "field")` | 表示/非表示 |
| `.bind_enabled_from(obj, "field")` | 有効/無効 |

バインドするフィールドは単純型（str, bool, int, float, list, dict）のみ。

## テーブル

- `ctx.table = ui.table(columns=..., rows=[], selection="multiple", row_key="name")`
- データ更新後は `ctx.table.update()` を呼ぶこと
- カスタムセル: `ctx.table.add_slot('body-cell-{field}')` でスロット定義
- 選択行の取得: `ctx.table.selected`（リスト）

## ダイアログ

- `dialog.submit(value)` で値を返して閉じる（`await dialog` で受け取る）
- `dialog.open()` / `dialog.close()` / `dialog.delete()`
- カスタムダイアログは `ui.dialog` を継承（参考: `common/folder_picker.py`）

## メニュー

再描画時は `menu.clear()` してから `with menu:` で再構築する。

## イベントハンドラ

- ループ内のラムダ: `lambda i=idx: handler(i)` （デフォルト引数でキャプチャ）
- JS + Python ハイブリッド: `js_handler='() => emit(value)'` → `handler=lambda e: process(e.args)`
- 複数アクション: `lambda: [func1(), func2()]`

## スタイリング

- `.classes()` → Tailwindクラス、`.style()` → インラインCSS、`.props()` → Quasar プロパティ
- メソッドチェーンで連結可能
- グローバルCSSは `app.py` の `header()` で定義（`.padd2`, `.padd4`, `.brdr` など）

## ページ・タブ構成

- ページ: `@ui.page("/path", title="...")` デコレータ
- タブ: `ui.tabs()` → `ui.tab_panels(tabs, value=initial_tab)`
- Ctx はページ内で1つ生成し、全タブで共有
