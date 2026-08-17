"""RoFormer の複数モデル直列推論 CLI。"""
import argparse
import json
import os
import sys
from pathlib import Path


sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from lib.roformer.task_infer import infer_roformer


def _print_marker(start: str, end: str, data: dict) -> None:
    """XtermDialog が解釈する JSON マーカーを出力する。"""
    print(start, flush=True)
    print(json.dumps(data, ensure_ascii=False), flush=True)
    print(end, flush=True)


class CliQueue:
    """Worker の Queue 出力を CLI の標準出力に変換する。"""

    def put(self, message: dict) -> None:
        message_type = message.get("type")
        if message_type == "log":
            print(message.get("text", ""), flush=True)
        elif message_type == "part":
            _print_marker(
                "[[[part_result_start]]]",
                "[[[part_result_end]]]",
                message.get("data", {}),
            )


def parse_args() -> argparse.Namespace:
    """CLI 引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="RoFormer モデルを指定順に適用します。",
    )
    parser.add_argument(
        "files",
        nargs="+",
        metavar="FILE",
        help="処理対象の音声ファイル（複数指定可）",
    )
    parser.add_argument(
        "-m",
        "--model",
        action="append",
        required=True,
        metavar="PATH",
        help="モデルファイル。適用順に複数回指定できます",
    )
    parser.add_argument(
        "--target-only",
        action="append",
        type=int,
        default=[],
        metavar="N",
        help="メイン stem のみ出力するモデル番号（1始まり、複数回指定可）",
    )
    parser.add_argument("--suffix", default="", help="出力ファイル名のサフィックス")
    parser.add_argument(
        "--format",
        choices=("wav", "flac"),
        default="wav",
        help="出力形式（デフォルト: wav）",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        metavar="DIR",
        help="出力先。省略時は入力ファイルと同じ場所",
    )
    parser.add_argument("--overlap", type=int, default=2, help="オーバーラップ（デフォルト: 2）")
    parser.add_argument(
        "--chunk-size",
        type=float,
        default=8.0,
        metavar="SECONDS",
        help="チャンクサイズ秒（デフォルト: 8）",
    )
    parser.add_argument("--subfolder", action="store_true", help="曲ごとのサブフォルダに出力")
    parser.add_argument(
        "--use-prefix-num",
        action="store_true",
        help="出力ファイル名に連番プレフィクスを付加",
    )
    args = parser.parse_args()

    invalid_indexes = [n for n in args.target_only if n < 1 or n > len(args.model)]
    if invalid_indexes:
        parser.error(
            f"--target-only は 1 から {len(args.model)} の範囲で指定してください: {invalid_indexes}"
        )
    if args.overlap < 1:
        parser.error("--overlap は1以上で指定してください")
    if args.chunk_size <= 0:
        parser.error("--chunk-size は0より大きい値で指定してください")
    return args


def build_task_data(args: argparse.Namespace) -> dict:
    """解析済み引数から既存の推論タスク用データを作る。"""
    target_only = set(args.target_only)
    models = [
        {
            "model": {
                "name": Path(model_path).stem,
                "path": model_path,
            },
            "target_only": index in target_only,
        }
        for index, model_path in enumerate(args.model, start=1)
    ]
    return {
        "models": models,
        "suffix": args.suffix,
        "fmt": f".{args.format}",
        "dest": "output_dir" if args.output_dir else "same",
        "overlap": args.overlap,
        "chunk_size": args.chunk_size,
        "subfolder": args.subfolder,
        "use_prefix_num": args.use_prefix_num,
        "files": args.files,
        "output_dir": args.output_dir,
    }


def main() -> int:
    """CLI 引数からタスクを構築し、選択順にモデルを適用する。"""
    try:
        data = build_task_data(parse_args())
        _print_marker(
            "[[[initial_result_start]]]",
            "[[[initial_result_end]]]",
            {"count": len(data.get("files", []))},
        )
        result = infer_roformer(data, CliQueue())  # type: ignore[arg-type]
        return 0 if result is not None else 1
    except Exception as e:
        print(f"[エラー] {e}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


