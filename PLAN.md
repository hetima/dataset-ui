# NiceGUI + React DAW 実装計画

## 前提と判断

- `edit/edit_daw_tab.py` から DAW 画面を開く。
- DAW 本体は `daw/` の Vite + React アプリとして実装する。
- 波形編集は `@waveform-playlist/browser` を中心に使う。型定義上、再生/停止、mute/solo、トラック音量、マスターボリューム、undo/redo、クリップ分割、WAV 書き出しを利用できる。
- 音声配信は NiceGUI の `app.add_media_files` を使う。
- React 側に OS の絶対パスを渡してよい。将来的な DAW project / AAF 相当の書き出しで元ファイル参照が必要になる可能性があるため、トラック情報に `sourcePath` として保持する。
- 音声取得そのものは NiceGUI の media URL を使う。ブラウザが直接ローカルファイルを読みに行く構成にはしない。
- 初回保存形式は WAV とする。元ファイル形式への再エンコードが必要なら、サーバー側で ffmpeg 等の導入可否を別途判断する。

## 成功条件

1. edit の DAW タブから選択中の音声ファイルを React DAW に渡せる。
2. React DAW が NiceGUI から発行された URL で複数トラックを読み込める。
3. 1 画面で再生/停止、solo/mute、マスターボリューム、トラック音量、ズーム、クリップ移動、カット、undo/redo ができる。
4. コンピング用の範囲選択を保持し、重複範囲を破綻なく扱える。
5. 編集結果を WAV Blob と編集メタデータとして NiceGUI に返し、`cnfg.outputs_dir` 以下へ保存できる。
6. `pnpm build` と NiceGUI 経由のブラウザ動作確認が通る。

## 実装方針

### 1. NiceGUI 側の起動口

対象ファイル: `edit/edit_daw_tab.py`, `edit/index.py`

- `edit/index.py` に DAW タブを追加する。
- `edit_daw_tab.py` に「選択ファイルを DAW で開く」ボタンを置く。
- ボタン押下時に `ctx.target_files()` を取得する。
- 対象なしの場合は `ui.notify` で止める。
- 対象ありの場合は DAW セッションを作成する。

検証:

- ファイル未選択で警告が出る。
- ファイル選択時に DAW タブへ遷移できる。

### 2. DAW セッション管理

対象ファイル候補: `edit/daw_session.py`, `edit/edit_daw_tab.py`

- セッション ID を生成し、以下をサーバー側に保持する。
  - 元ファイルパス
  - 表示名
  - `app.add_media_files` で公開したメディア URL
  - 保存先候補
- メディア公開パスは衝突しにくい名前にする。
  - 例: `/daw-media/{session_id}/{track_index}`
  - 親フォルダ名だけを mount に使う実装は同名フォルダで衝突しやすいため避ける。
- セッションの寿命はアプリ起動中のみでよい。永続化は後続。

検証:

- 同名ファイルや同名親フォルダがあっても別 URL になる。
- React 側に `sourcePath` が渡り、編集メタデータや project 書き出し用に保持できる。

### 3. NiceGUI API

対象ファイル候補: `edit/daw_api.py`, `app.py`

追加する API:

- `GET /api/daw/session/{session_id}`
  - React 初期化用 JSON を返す。
  - 例: `tracks: [{ id, name, sourcePath, url, volume, muted, soloed, startTime }]`
- `POST /api/daw/save/{session_id}`
  - `multipart/form-data` で WAV Blob と編集メタデータ JSON を受け取る。
  - `cnfg.outputs_dir` 以下に保存する。
  - 保存名は衝突回避する。
- 必要なら `POST /api/daw/project/{session_id}` を後続で追加し、音声を書き出さず編集状態だけ保存する。

検証:

- API 単体でセッション JSON が返る。
- WAV Blob を受け取り、ファイルサイズ 0 ではない音声ファイルが保存される。

### 4. React アプリの組み込み

対象ファイル: `daw/vite.config.ts`, `daw/src/*`, `edit/edit_daw_tab.py`

- 開発時:
  - Vite dev server を `http://127.0.0.1:5173` で起動し、NiceGUI の iframe から開く。
  - API は NiceGUI に向ける。CORS 問題が出る場合は Vite proxy を設定する。
- 本番/通常起動時:
  - `pnpm build` の成果物 `daw/dist` を NiceGUI で static 配信する。
  - `edit_daw_tab.py` の iframe は `/daw/index.html?session=...` を開く。
- React 側は query string の `session` を読み、`GET /api/daw/session/{session}` で初期化する。
- React state では `sourcePath` と `url` を両方保持する。再生・波形ロードは `url`、編集メタデータ・将来の project/AAF 風書き出しは `sourcePath` を使う。

検証:

- dev server 経由と build 配信の両方で白画面にならない。
- iframe 内から NiceGUI の API と音声 URL を取得できる。

### 5. DAW 画面構成

対象ファイル候補:

- `daw/src/App.tsx`
- `daw/src/components/Toolbar.tsx`
- `daw/src/components/TrackList.tsx`
- `daw/src/components/PlaylistEditor.tsx`
- `daw/src/api.ts`
- `daw/src/types.ts`

画面は 1 画面完結にする。

- 上部ツールバー:
  - 再生、停止、先頭へ戻る
  - undo、redo
  - カット
  - 保存
  - ズーム
  - マスターボリューム
- 左トラックヘッダー:
  - トラック名
  - solo
  - mute
  - volume
  - 必要なら pan
- 中央:
  - `WaveformPlaylistProvider`
  - `PlaylistVisualization`
  - `KeyboardShortcuts`
- 見た目:
  - アイコンは `lucide-react` を使う。
  - 操作用 UI はコンパクトにし、説明文は置きすぎない。

検証:

- 再生/停止が効く。
- solo/mute/volume が音に反映される。
- undo/redo ボタンの disabled 状態が `canUndo` / `canRedo` と同期する。

### 6. waveform-playlist 連携

使用予定 API:

- `useAudioTracks`
- `WaveformPlaylistProvider`
- `PlaylistVisualization`
- `usePlaylistControls`
- `usePlaylistState`
- `usePlaylistData`
- `useClipSplitting`
- `KeyboardShortcuts`
- `useExportWav`

実装ポイント:

- `useAudioTracks` に NiceGUI から返った URL を渡し、`ClipTrack[]` を作る。
- `onTracksChange` で移動、トリム、分割後の `tracks` を React state に戻す。
- `KeyboardShortcuts` で再生、カット、undo/redo を割り当てる。
- 保存時は `useExportWav().exportWav(tracks, trackStates, { mode: "master", autoDownload: false })` を使い、返った Blob を NiceGUI に POST する。

検証:

- クリップ移動後に再レンダリングしても位置が戻らない。
- カット後に undo/redo できる。
- 書き出し WAV が編集後の配置を反映する。

### 7. コンピング

最初の実装では「複数テイクから有効範囲を選ぶ」機能として扱う。

- 各トラックをテイクとして表示する。
- 選択範囲を comp segment として保持する。
- 同じ時間帯に複数 segment が重なった場合は、最後に選択した segment を優先し、他の segment は短縮または無効化する。
- comp segment は JSON として保存 API に渡す。
- 書き出し時は comp segment に基づき、採用外の範囲を mute または分割/削除した `tracks` から master WAV を作る。

検証:

- 複数トラックで同じ時間帯を選んでも、採用範囲が 1 つに確定する。
- comp segment JSON を保存し、再ロード時に同じ範囲を復元できる。
- comp 結果の WAV で採用範囲だけが鳴る。

## 実装順

1. NiceGUI に DAW タブとセッション API を追加する。
   - verify: `GET /api/daw/session/{id}` が選択ファイル情報を返す。
2. React で session 読み込みと複数トラック表示を作る。
   - verify: `pnpm build` が通り、iframe で波形が表示される。
3. 基本操作ツールバーを実装する。
   - verify: 再生/停止、solo/mute、volume、zoom が動く。
4. クリップ編集と undo/redo を接続する。
   - verify: 移動、カット、undo/redo が state に残る。
5. 保存 API と WAV 書き出しを接続する。
   - verify: NiceGUI 側に WAV が保存され、再生できる。
6. コンピング UI と comp segment 保存を追加する。
   - verify: 採用範囲の重複解決と書き出し結果を確認する。

## 未確定点

- 保存形式を WAV 固定にするか、元ファイル形式へ変換するか。
- 長時間音声や多数トラックでブラウザメモリが足りるか。
- comp segment を waveform-playlist のクリップ分割で表現するか、独自レイヤーで保持するか。
- Vite dev server を NiceGUI から自動起動するか、開発者が別ターミナルで起動するか。
- project/AAF 相当の書き出し形式を独自 JSON にするか、既存 DAW 互換形式を目指すか。

## 最小マイルストーン

最初の完成ラインは「選択した複数ファイルを DAW で開き、再生/停止、mute/solo、音量、クリップ移動、カット、undo/redo、WAV 保存ができる」までとする。コンピングはこの上に追加し、既存の基本編集を壊さない範囲で段階的に入れる。
