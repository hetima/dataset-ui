# dataset-ui

ACE-Step / Qwen3-ASR 向けの音声データセット・メタデータ一括編集 Web UI。

## 技術スタック

- **フレームワーク**: NiceGUI（Python製WebフレームワークでブラウザUIを構築）
- **音声処理**: librosa, soundfile, mutagen
- **AI モデル**: Qwen3-ASR（音声認識）、BS-RoFormer（音源分離）、ACE-Step（音楽トランスクリプション）
- **深層学習**: transformers, torch, accelerate, bitsandbytes

## 起動方法

```bash
python app.py [--host 127.0.0.1] [--port 7869] [--native] [--auto-reload]
```

起動後、`http://127.0.0.1:7869` でアクセス可能。`--auto-reload` は開発時に使用。

## ディレクトリ構成

```
app.py                    # エントリーポイント（NiceGUI、ルーティング）
config.json               # 永続設定（モデルパス、フォルダ等）
requirements.txt
music/                    # Music モジュール（楽曲メタデータ編集）
│   index.py              # ページ定義（タブレイアウト）
│   music_app_ctx.py      # bindable_dataclass による状態管理
│   music_main_tab.py     # メインUI（ファイル読込・分析・トランスクリプション）
│   music_setting_tab.py  # 設定UI
│   musicfile.py          # MusicFile データクラス
│   musicanalyze.py       # BPM・キー・拍子解析エンジン
│   acestep_transcriptor.py
voice/                    # Voice モジュール（音声データセット編集）
│   index.py
│   voice_app_ctx.py
│   voice_main_tab.py     # メインUI（音声認識・分割処理）
│   voice_setting_tab.py
│   voicefile.py          # VoiceFile データクラス（親子階層）
│   qwen3_asr_transcriptor.py
│   segment_silence.py    # 無音検出分割
│   segment_equally.py    # 等間隔分割
common/                   # 共通モジュール
│   worker.py             # マルチプロセスバックグラウンドタスク実行
│   setting.py            # config.json の読み書き
│   file_util.py          # 音声ファイル検出・ソート
│   folder_picker.py, local_file_picker.py, message_dialog.py
│   download_repo.py, download_ckpt.py
│   xterm_dialog.py
qwen_asr/                 # Qwen3-ASR 実装（同梱、--no-deps でインストール）
roformer/                 # MelBandRoFormer 音源分離モデル（同梱）
cli/                      # スタンドアロン CLI ツール（HF モデルダウンロード等）
var/                      # 試験的スクリプト — メインアプリの一部ではない
```

## 主要な設計パターン

### 状態管理（Ctx パターン）

`MusicCtx` / `VoiceCtx` は `@binding.bindable_dataclass` — UI 要素をフィールドにバインドする。コールバックリスト（`model_refresh_func`、`dataset_dirs_refresh_func`）で設定変更を UI に通知する。

### Worker / Generator コントラクト

バックグラウンドタスクは `(progress: float, status: str, partial_result: dict | None)` を yield するジェネレータ関数として実装し、最終結果の dict を return する。キャンセルは `stop_event.is_set()` で確認する。

```python
def task(data, stop_event):
    yield 0.0, "開始", None
    for i, item in enumerate(items):
        if stop_event.is_set():
            return {}
        yield (i+1)/len(items), f"処理中 {i+1}/{len(items)}", None
    return final_results
```

### File データクラス

`MusicFile` / `VoiceFile` は属性アクセスと dict アクセスの両方をサポート（`file["path"]` ↔ `file.path`）。シリアライズは `.to_dict()` / `.from_dict()` を使う。内部の `_data` に直接アクセスしない。

## 規約

- **言語**: UI テキストとコメントは**日本語**で統一する
- **設定**: すべての設定は `config.json` に保存。`common/setting.py` 経由でアクセスし、直接読み書きしない
- **モデル**: `config.json` で設定した `models_dir` 以下に配置。フルパスではなくサブフォルダ名で参照する
- **音声フォーマット**: `.wav`, `.flac`, `.mp3`, `.m4a`, `.ogg`, `.aac` をサポート（詳細は `voicefile.py` / `musicfile.py` 参照）
- **CSS**: NiceGUI の `classes()` と `style()` チェーンを使う。グローバルスタイルは `app.py` の `header()` で定義

## テスト

正式なテストフレームワークはなし。`var/test*.py` に試験的スクリプト。
開発時は `--auto-reload` + ブラウザで動作確認。
