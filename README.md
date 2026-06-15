# dataset-ui

オーディファイルに様々な処理を施すWeb UIです。


## voice
主に音声データを扱うページ
- LFM2.5-Audio-1.5B-JP、Qwen3-ASR での書き起こし
- 無音区間で分割、均等に分割
- タイムストレッチ
- Irodori-TTS のトレーニング
- Irodori-TTS の推論

## music
主に音楽データを扱うページ
- Roformer での音声分離
- BPM、キー、拍子の解析
- ACE-Step Transcriber で歌詞を解析

音声分離は MelBand Roformer と BS Roformer に対応しています。


## audio-edit
オーディファイルを編集するページ
書き出しフォルダのファイルをDAW風のUIでマルチトラック編集できます。\
コンピングとかも一応できます。編集結果を書き出すことができます。\
編集状態は保存できませんが、AAFに書き出せます。コンピングのリージョンはそれぞれのオーディオイベントに変換されます。


## cli/lfm_server.py
LFM2.5-Audio-1.5B-JPでASRを行うOpenAI互換APIサーバです。姉妹品の [dataset-ui-app](https://github.com/hetima/dataset-ui-app) から利用できます。ベースURLは `http://localhost:7868/v1` です。APIキーは不要です。モデル名も不要ですが、`/models` は `auto` を返します。

```sh
# 起動方法
# venvを有効するか .venv/Scripts/python.exe で
python cli/lfm_server.py --port 7868 --model-dir LFM2.5-Audio-1.5B-JPのフォルダのパス
```


## インストール
```
git clone https://github.com/hetima/dataset-ui
```
venv を作ってください。バージョンは3.12で開発してます。torch 関連は requirements.txt に書いてないので手動でお好みのものを入れてください。ちなみに2.10.0を入れて開発してます。

```
pip install torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 --index-url https://download.pytorch.org/whl/cu130
pip install -r requirements.txt
```

`app.py` を実行すると web UI が開きます。


## その他説明
各ページの設定タブで書き出しフォルダとモデルフォルダ、トレーニングフォルダは必ず確認することをお勧めします。初期設定ではレポジトリの中に作成されます。この3つの設定はすべてのページで共有されます。

自動保存されない操作が多いので保存ボタンを押し忘れないように注意してください。

モデルを選択するコンボボックスでは、リポジトリ形式のモデルID（user/model）を指定すると huggingface からダウンロードします（デフォルトのキャッシュにダウンロードされ再利用されます）。「ダウンロード」を押すとモデルフォルダにダウンロードされます。

ダウンロードが途中で止まる場合は手動でダウンロードして配置してください。hf-xetをアンインストールすると改善する場合があります。

```
pip uninstall hf-xet
```


## スクリーンショット

voice
![Screenshot](https://raw.githubusercontent.com/hetima/dataset-ui/main/assets/01.jpg)

Irodori-TTS
![Screenshot](https://raw.githubusercontent.com/hetima/dataset-ui/main/assets/02.jpg)

audio-edit
![Screenshot](https://raw.githubusercontent.com/hetima/dataset-ui/main/assets/03.jpg)


## 開発環境
Pyrhon 3.12 で開発しています。Web UI のフレームワークは NiceGUI です。\
daw フォルダの中は Node.js プロジェクトです。パッケージマネージャーは `pnpm` を使っています。

```
cd daw
pnpm build
pnpm deploy
```

`deploy` で `publish\daw_ui` にコピーされて使えるようになります。

`app.py` に引数 `--develop-mode` をつけて起動すると、pyファイルを編集すると自動でリロードされるようになります。開発時以外は邪魔なので気をつけてください。また、`daw_ui` を見に行く先が `deploy` されたパスではなく `daw\dist` に変わります。


## 使用したライブラリなど

- [zauberzeug/nicegui](https://github.com/zauberzeug/nicegui/)
- [Aratako/Irodori-TTS](https://github.com/Aratako/Irodori-TTS)
- [Aratako/Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server)
- [naomiaro/waveform-playlist](https://github.com/naomiaro/waveform-playlist)
- [sampotts/plyr](https://github.com/sampotts/plyr)
- [Qwen3-ASR support-transformers-v5.4](https://github.com/One-sixth/Qwen3-ASR/tree/support-transformers-v5.4)


## モデルライセンス
- Irodori-TTS: MIT License
- LFM2.5-Audio-1.5B-JP: [LFM Open License v1.0](https://huggingface.co/LiquidAI/LFM2.5-Audio-1.5B-JP/blob/main/LICENSE)
- Qwen3-ASR: Apache License 2.0
- acestep-transcriber: MIT License

## ライセンス
MIT License
