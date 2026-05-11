---
description: "バックグラウンド処理タスクを追加する。新しいオーディオ処理・解析機能をWorker/Generatorパターンで実装する際に使用。"
name: "Add Processing Task"
argument-hint: "タスク名と処理内容の説明"
---

バックグラウンド処理タスクを追加してください。

## 入力

タスク名: $ARGUMENT

## 実装要件

以下の3ファイルを作成・修正すること:

### 1. 処理関数の作成（`{module}/` に新規ファイル）

Worker/Generatorパターンに従う:

```python
def {task}_main(data: dict, stop_event) -> Generator[tuple[float, str, dict | None], None, dict]:
    """バックグラウンド処理タスク

    Args:
        data: 処理に必要なデータ（ファイルパスリスト、パラメータ等）
        stop_event: キャンセル検知用イベント

    Yields:
        (progress, status_text, partial_result) のタプル

    Returns:
        最終結果のdict
    """
    file_paths = data["file_paths"]
    # 必要に応じて他のパラメータを取り出す

    yield 0.0, "開始", None

    for i, path in enumerate(file_paths):
        if stop_event.is_set():
            return {}

        # ここに処理を書く

        progress = (i + 1) / len(file_paths)
        yield progress, f"処理中 {i+1}/{len(file_paths)}", None

    return {"result": results}
```

### 2. Ctx へのメソッド追加（`{module}/{module}_app_ctx.py`）

完了時のコールバックメソッドを追加:

```python
def {task}_completed(self, result: dict):
    """処理完了時にWorkerから呼ばれる"""
    with self.client:
        if result:
            # 結果をfilesに反映し、テーブルを更新
            self.table.update()
            ui.notify("処理が完了しました", type="positive")
        else:
            ui.notify("処理がキャンセルされました", type="warning")
```

### 3. メインタブにUI追加（`{module}/{module}_main_tab.py`）

ボタンとハンドラを追加:

```python
async def on_{task}():
    selected = ctx.table.selected
    if not selected:
        ui.notify("ファイルを選択してください", type="warning")
        return
    file_paths = [row["path"] for row in selected]
    data = {"file_paths": file_paths}
    await ctx.worker.run({task}_main, data, ctx.{task}_completed)

ui.button("タスク名", on_click=on_{task}).bind_enabled_from(ctx.worker, "can_run")
```

## 参照パターン

- 既存の実装を参考にすること:
  - 音声分析: [music/musicanalyze.py](music/musicanalyze.py)
  - 文字起こし: [voice/qwen3_asr_transcriptor.py](voice/qwen3_asr_transcriptor.py)
  - セグメント分割: [voice/segment_silence.py](voice/segment_silence.py)
- Workerの仕組み: [common/worker.py](common/worker.py)
- Ctxパターン: [voice/voice_app_ctx.py](voice/voice_app_ctx.py), [music/music_app_ctx.py](music/music_app_ctx.py)

## 注意事項

- UIテキストとコメントは**日本語**で書く
- `stop_event.is_set()` のチェックをループ内で必ず行う
- `yield` の progress は 0.0〜1.0 の範囲
- Ctx メソッド内で `ui.notify()` を呼ぶ際は `with self.client:` でラップする
- 音声フォーマットの判定は `voicefile.py` / `musicfile.py` の定義を参照
