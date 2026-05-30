CLI タスクを追加してください。

## 入力

タスク名と処理内容: $ARGUMENTS

## 実装要件

以下の3ファイルを作成・修正すること:

### 1. CLI スクリプトの作成（`{module}/cli_task_{task}.py` として新規ファイル）

- stdin から JSON を受け取り、処理結果をマーカー形式で stdout に出力する
- プロジェクト外部ライブラリのみ依存（`common/` や `{module}/` の import は避け、必要なコードは直接コピーする）

```python
"""
{処理の説明}
stdin: JSON（処理対象データ）
stdout: マーカー形式で結果を出力
"""
import json
import sys


def main():
    data = json.loads(sys.stdin.read())
    items = data  # またはdata["files"]等、入力形式に合わせる
    total = len(items)

    if total == 0:
        return

    # 件数を通知
    print("[[[initial_result_start]]]", flush=True)
    print(json.dumps({"count": total}), flush=True)
    print("[[[initial_result_end]]]", flush=True)

    for i, item in enumerate(items, start=1):
        print(f"処理中 ({i}/{total}): {item}", flush=True)
        try:
            result = process(item)  # ここに処理を書く
            print("[[[part_result_start]]]", flush=True)
            print(json.dumps({"data": result}), flush=True)
            print("[[[part_result_end]]]", flush=True)
        except Exception as e:
            print(f"エラー: {item}: {e}", flush=True)


if __name__ == "__main__":
    main()
```

### 2. Ctx へのメソッド追加（`{module}/{module}_app_ctx.py`）

part_callback から1件ずつ呼ばれるメソッドを追加:

```python
def progress_{task}(self, result_files: list) -> None:
    """CLI タスクから1件ずつ結果を受け取る"""
    for music_file in self.files:
        info = next((d for d in result_files if d["path"] == music_file.path), None)
        if info is None:
            continue
        # 結果をfilesに反映
        music_file.some_field = info.get("some_field", music_file.some_field)
    self.table.update()
```

### 3. メインタブにUI追加（`{module}/{module}_main_tab.py`）

ボタンとハンドラを追加:

```python
def progress_{task}(part: dict) -> None:
    ctx.progress_{task}([part["data"]])

def on_{task}() -> None:
    files = ctx.target_files()
    paths = [f["path"] for f in files]  # type: ignore
    if not paths:
        ui.notify("処理対象がありません")
        return
    cli = str(Path(__file__).parent / "cli_task_{task}.py")
    dlg = XtermDialog(
        args=[sys.executable, cli],
        title="{処理タイトル}",
        input_json=paths,
        part_callback=progress_{task},
    )
    dlg.open()

ui.button("{ボタンラベル}", on_click=on_{task})
```

## 参照パターン

- 既存の CLI タスク実装: [music/cli_task_musicanalyze.py](music/cli_task_musicanalyze.py)
- XtermDialog: [common/xterm_dialog.py](common/xterm_dialog.py)
- Ctx パターン: [music/music_app_ctx.py](music/music_app_ctx.py), [voice/voice_app_ctx.py](voice/voice_app_ctx.py)

## 注意事項

- UIテキストとコメントは**日本語**で書く
- CLI スクリプトはスタンドアロンで動作すること（`common/` や `{module}/` に依存しない）
- `print(..., flush=True)` を必ず付ける（バッファリング防止）
- マーカー文字列は固定: `[[[initial_result_start]]]` / `[[[initial_result_end]]]` / `[[[part_result_start]]]` / `[[[part_result_end]]]`
- `input_json` に渡すデータは `json.dumps` できる Python オブジェクトであること
- 音声フォーマットの判定は `voicefile.py` / `musicfile.py` の定義を参照
