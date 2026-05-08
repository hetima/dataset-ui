import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class VoiceFile:
    name: str
    path: str
    caption: Optional[str]

    def __getitem__(self, key: str):
        return getattr(self, key)

    def __setitem__(self, key: str, value):
        setattr(self, key, value)

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def keys(self):
        return vars(self).keys()

    def values(self):
        return vars(self).values()

    def items(self):
        return vars(self).items()

    def as_dict(self):
        return asdict(self)

    def to_dict(self) -> dict:
        """VoiceFile の各フィールドを辞書として返す"""

        return {
            "name": self.name,
            "path": self.path,
            "caption": self.caption,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VoiceFile":
        """辞書から VoiceFile インスタンスを生成する"""

        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            caption=data.get("caption", ""),
        )

    def save_to_json(self) -> None:
        """音声ファイルと同名の .json にメタデータを書き出す（存在すれば上書き）"""
        pass

    def save_to_txt(self) -> None:
        output = self.caption
        if output:
            txt_path = Path(self.path).with_suffix(".txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(output.strip())

    @classmethod
    def from_audio_file(cls, file: Path) -> "VoiceFile":
        txt_path = file.with_suffix(".txt")
        name = file.name
        path = str(file)
        caption = ""

        # txtが存在する場合は読み込み
        if txt_path.exists():
            with open(txt_path, "r", encoding="utf-8") as f:
                text = f.read()

            caption = text.strip()

        return cls(
            name=name,
            path=path,
            caption=caption,
        )
