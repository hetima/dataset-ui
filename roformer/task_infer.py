"""CpuTaskDialog 用 Roformer 推論タスク。"""
import multiprocessing
import multiprocessing.queues


def _log(queue: multiprocessing.queues.Queue, text: str):  # type: ignore[type-arg]
    queue.put({"type": "log", "text": text})


def infer_roformer(data: dict, queue: multiprocessing.queues.Queue, stop_event) -> dict | None:  # type: ignore[type-arg]
    """
    data keys:
      model     : dict  (list_roformer_models の1エントリ)
      suffix    : str   (出力ファイル名サフィックス)
      fmt       : str   (".wav" | ".flac")
      dest      : str   ("output_dir" | "")
      cache     : bool  (モデルをキャッシュするか)
      files     : list[str]  (処理対象ファイルパス)
      output_dir: str   (dest=="output_dir" のときの出力先)
    """
    model: dict = data["model"]
    suffix: str = data["suffix"]
    fmt: str = data["fmt"]
    dest: str = data["dest"]
    cache: bool = data["cache"]
    files: list[str] = data["files"]
    output_dir: str = data.get("output_dir", "")

    from pathlib import Path

    _log(queue, f"モデル: {model.get('name', '')}")
    _log(queue, f"ファイル数: {len(files)}")

    for file_path in files:
        if stop_event.is_set():
            return None
        out_dir = output_dir if output_dir else str(Path(file_path).parent)
        # TODO: 推論処理を実装する
        _log(queue, f"  → {out_dir}")

    return {"processed": len(files)}
