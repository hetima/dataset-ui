"""XtermDialogの動作確認用CLIスクリプト。環境変数を列挙する。"""
import os

for key, value in sorted(os.environ.items()):
    print(f"{key}={value}", flush=True)

print("\n完了！", flush=True)
