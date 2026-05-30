"""XtermDialogの動作確認用CLIスクリプト。tqdmで10秒間進捗を表示するだけ。"""
import time
from tqdm import tqdm

for _ in tqdm(range(10), desc="テスト処理中"):
    time.sleep(1)

print("完了！")
