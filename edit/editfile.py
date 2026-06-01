from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class EditFile:
    name: str
    path: str

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
        return {k: v for k, v in asdict(self).items() if k != "default"}

    def to_dict(self) -> dict:
        """VoiceFile の各フィールドを辞書として返す"""

        return {
            "name": self.name,
            "path": self.path,
        }

    def add_child(self, child: "EditFile") -> None:
        """子要素を追加する"""
        if self.children is None:
            self.children = []
        self.children.append(child)
        self.is_expandable = True

    @classmethod
    def from_dict(cls, data: dict) -> "EditFile":
        """辞書から VoiceFile インスタンスを生成する"""

        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
        )

    def save_to_json(self) -> None:
        """音声ファイルと同名の .json にメタデータを書き出す（存在すれば上書き）"""
        pass

    @classmethod
    def from_audio_file(cls, file: Path) -> "EditFile":
        file = Path(file)
        txt_path = file.with_suffix(".txt")
        name = file.name
        path = str(file)
        caption = ""

        # txtが存在する場合は読み込み
        if txt_path.exists():
            with open(txt_path, "r", encoding="utf-8") as f:
                text = f.read()

            caption = text.strip()

        default = cls(
            name=name,
            path=path,
        )

        return cls(
            name=name,
            path=path,
        )
