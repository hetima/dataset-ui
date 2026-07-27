"""ThreadTaskDialog用のYingMusic-SVC推論タスク。"""

import queue
import subprocess
import threading
import time
from pathlib import Path


def _log(q: queue.Queue, text: str) -> None:  # type: ignore[type-arg]
    q.put({"type": "log", "text": text})


def _python_path(repository_dir: Path, venv_dir: str) -> Path:
    """設定値とリポジトリ位置からYingMusic-SVC用Pythonを解決する。"""
    candidates: list[Path] = []
    if venv_dir:
        configured = Path(venv_dir)
        candidates.extend((configured / "Scripts" / "python.exe", configured))
    candidates.extend(
        (
            repository_dir / ".venv" / "Scripts" / "python.exe",
            repository_dir.parent / ".venv" / "Scripts" / "python.exe",
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("YingMusic-SVC用venvのpython.exeが見つかりません")


def _terminate_process_tree(process: subprocess.Popen) -> None:  # type: ignore[type-arg]
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
        capture_output=True,
        check=False,
    )


def _run_command(
    args: list[str],
    repository_dir: Path,
    stop_event: threading.Event,
) -> bool:
    """Ying用Pythonを直接起動し、親ターミナルへ出力する。"""
    process = subprocess.Popen(
        args,
        cwd=repository_dir,
    )

    while process.poll() is None:
        if stop_event.is_set():
            _terminate_process_tree(process)
            return False
        time.sleep(0.1)

    if process.returncode != 0:
        raise RuntimeError(f"YingMusic-SVCが終了コード {process.returncode} で終了しました")
    return True


def run_ying_infer(
    data: dict,
    q: queue.Queue,  # type: ignore[type-arg]
    stop_event: threading.Event,
) -> dict | None:
    """選択された参照音声ごとにYingMusic-SVC CLIを順番に実行する。"""
    repository_dir = Path(data["repository_dir"])
    script_path = repository_dir / "z_inference.py"
    if not script_path.is_file():
        raise FileNotFoundError(f"z_inference.pyが見つかりません: {script_path}")
    python_path = _python_path(repository_dir, data.get("venv_dir", ""))

    refs: list[str] = data["refs"]
    q.put({"type": "progress", "value": 0, "max": len(refs)})
    _log(q, "進行状況は本物のターミナルを参照してください")

    for index, ref in enumerate(refs):
        if stop_event.is_set():
            return None
        _log(q, f"推論 [{index + 1}/{len(refs)}]: {Path(ref).name}")
        args = [
            str(python_path),
            str(script_path),
            "--src",
            data["source"],
            "--base-checkpoint",
            data["base_checkpoint"],
            "--lora",
            data["lora"],
            "--ref",
            ref,
            "--lora-scale",
            str(data["lora_scale"]),
            "--steps",
            str(data["steps"]),
            "--format",
            data["format"],
            "--output-path",
            data["output_path"],
        ]
        if data.get("pitch_shift") is not None:
            args.extend(("--pitch-shift", str(data["pitch_shift"])))
        if not _run_command(args, repository_dir, stop_event):
            return None
        q.put({"type": "progress", "value": index + 1})

    return {"count": len(refs)}
