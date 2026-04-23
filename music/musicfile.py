import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import re

@dataclass
class MusicFile:
    name: str
    path: str
    lyrics: str
    caption: str
    bpm: str
    keyscale: str
    timesignature: str
    language: str
    duration: str
    
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
        """MusicFile の各フィールドを辞書として返す"""
        return {
            "name": self.name,
            "path": self.path,
            "lyrics": self.lyrics,
            "caption": self.caption,
            "bpm": self.bpm,
            "keyscale": self.keyscale,
            "timesignature": self.timesignature,
            "language": self.language,
            "duration": self.duration,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MusicFile":
        """辞書から MusicFile インスタンスを生成する"""
        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            lyrics=data.get("lyrics", ""),
            caption=data.get("caption", ""),
            bpm=str(data.get("bpm", "")),
            keyscale=data.get("keyscale", ""),
            timesignature=data.get("timesignature", ""),
            language=data.get("language", ""),
            duration=data.get("duration", ""),
        )

    def save_to_json(self) -> None:
        """音声ファイルと同名の .json にメタデータを書き出す（存在すれば上書き）"""
        json_path = Path(self.path).with_suffix(".json")

        # bpm は数値として保存できれば変換する
        data = {
            "caption": self.caption,
            "bpm": str(self.bpm),
            "keyscale": self.keyscale,
            "timesignature": self.timesignature,
            "language": self.language,
            "duration": self.duration,
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_to_lyrics(self) -> None:
        """音声ファイルと同名の .lyrics.txt に歌詞を書き出す（存在すれば上書き、空なら何もしない）"""
        if not self.lyrics.strip():
            return

        lyrics_path = Path(self.path).with_suffix(".lyrics.txt")
        with open(lyrics_path, "w", encoding="utf-8") as f:
            f.write(self.lyrics)

    def save_to_aitk(self) -> None:
        output = f"<CAPTION>\n{self.caption}\n</CAPTION>\n"
        output += f"<LYRICS>\n{self.lyrics}\n</LYRICS>\n"
        output += f"<BPM>{self.bpm}</BPM>\n"
        output += f"<KEYSCALE>{self.keyscale}</KEYSCALE>\n"
        output += f"<TIMESIGNATURE>{self.timesignature}</TIMESIGNATURE>\n"
        output += f"<DURATION>{self.duration}</DURATION>\n"
        output += f"<LANGUAGE>{self.language}</LANGUAGE>"
        aitk_path = Path(self.path).with_suffix(".txt")
        with open(aitk_path, "w", encoding="utf-8") as f:
            f.write(output)

    @classmethod
    def from_audio_file(cls , file:Path) -> "MusicFile":
        json_path = file.with_suffix(".json")
        lyrics_path = file.with_suffix(".lyrics.txt")
        aitk_path = file.with_suffix(".txt")

        name = file.name
        path = str(file)
        lyrics = ""
        caption = ""
        bpm = ""
        keyscale = ""
        timesignature = ""
        language = ""
        duration = ""

        # txtが存在する場合は読み込み
        if aitk_path.exists():
            with open(aitk_path, "r", encoding="utf-8") as f:
                text = f.read()

            def tag(name):
                m = re.search(rf"<{name}>(.*?)</{name}>", text, re.DOTALL)
                return m.group(1).strip() if m else ""

            caption = tag("CAPTION")
            lyrics = tag("LYRICS")
            bpm = tag("BPM")
            keyscale = tag("KEYSCALE")
            timesignature = tag("TIMESIGNATURE")
            duration = tag("DURATION")
            language = tag("LANGUAGE")

        # lyrics.txtが存在する場合は読み込み
        if lyrics_path.exists():
            with open(lyrics_path, "r", encoding="utf-8") as f:
                lyrics = f.read().strip()

        # jsonが存在する場合は読み込んで各変数に反映
        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            caption = data.get("caption", caption)
            bpm = str(data.get("bpm", bpm))
            keyscale = data.get("keyscale", keyscale)
            timesignature = data.get("timesignature", timesignature)
            language = data.get("language", language)
            duration = data.get("duration", duration)

        return cls(
            name=name,
            path=path,
            lyrics=lyrics,
            caption=caption,
            bpm=bpm,
            keyscale=keyscale,
            timesignature=timesignature,
            language=language,
            duration=duration,
        )
