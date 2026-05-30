"""XtermDialogの動作確認用CLIスクリプト。tqdmで10秒間進捗を表示しつつマーカー形式でJSONを出力する。"""
import json
import time
from tqdm import tqdm

TOTAL = 10
print("[[[initial_result_start]]]", flush=True)
print(json.dumps({"count": TOTAL}), flush=True)
print("[[[initial_result_end]]]", flush=True)

for i in tqdm(range(TOTAL), desc="テスト処理中"):
    time.sleep(1)
    print("[[[part_result_start]]]", flush=True)
    print(json.dumps({"step": i + 1, "message": f"ステップ {i + 1} 完了"}), flush=True)
    print("[[[part_result_end]]]", flush=True)

print("完了！")
