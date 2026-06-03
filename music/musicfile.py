import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
from common.file_util import Mtdt
import re

try:
    from mutagen import File as MutagenFile
except ImportError:
    MutagenFile = None

@dataclass
class MusicFile:
    name: str
    path: str
    lyrics: Optional[str]
    synced_lyrics: Optional[str]
    caption: Optional[str]
    bpm: Optional[str]
    keyscale: Optional[str]
    timesignature: Optional[str]
    language: Optional[str]
    duration: Optional[str]
    title: Optional[str] = None
    artist: Optional[str] = None
    album_artist: Optional[str] = None
    ttml: Optional[str] = None
    default: Optional["MusicFile"] = None
    is_expandable: bool = False
    children: Optional[list["MusicFile"]] = None

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

    def to_mtdt(self) -> dict:
        """mtdt用の辞書を返す"""
        return {
            "lyrics": self.lyrics,
            "synced_lyrics": self.synced_lyrics,
            "caption": self.caption,
            "bpm": self.bpm,
            "keyscale": self.keyscale,
            "timesignature": self.timesignature,
            "language": self.language,
            "duration": self.duration,
            "artist": self.artist,
            "album_artist": self.album_artist,
            "ttml": self.ttml,
        }

    def to_dict(self) -> dict:
        """MusicFile の各フィールドを辞書として返す"""
        return {
            "name": self.name,
            "path": self.path,
            "lyrics": self.lyrics,
            "synced_lyrics": self.synced_lyrics,
            "caption": self.caption,
            "bpm": self.bpm,
            "keyscale": self.keyscale,
            "timesignature": self.timesignature,
            "language": self.language,
            "duration": self.duration,
            "artist": self.artist,
            "album_artist": self.album_artist,
            "ttml": self.ttml,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MusicFile":
        """辞書から MusicFile インスタンスを生成する"""
        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            lyrics=data.get("lyrics", ""),
            synced_lyrics=data.get("synced_lyrics", ""),
            caption=data.get("caption", ""),
            bpm=str(data.get("bpm", "")),
            keyscale=data.get("keyscale", ""),
            timesignature=data.get("timesignature", ""),
            language=data.get("language", ""),
            duration=data.get("duration", ""),
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            album_artist=data.get("album_artist", ""),
            ttml=data.get("ttml", ""),
        )

    def add_child(self, child: "MusicFile") -> None:
        """子要素を追加する"""
        if self.children is None:
            self.children = []
        self.children.append(child)
        self.is_expandable = True

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
        if not self.lyrics:
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
    def from_audio_file(cls, file: Path, mtdt: "Mtdt|None" = None) -> "MusicFile":
        json_path = file.with_suffix(".json")
        lyrics_path = file.with_suffix(".lyrics.txt")
        aitk_path = file.with_suffix(".txt")

        name = file.name
        path = str(file)
        lyrics = ""
        synced_lyrics = ""
        ttml = ""
        caption = ""
        bpm = ""
        keyscale = ""
        timesignature = ""
        language = ""
        duration = ""

        title = ""
        artist = ""
        album_artist = ""

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

        # mtdt.json
        mtdt_data = mtdt.song_data(name) if mtdt else None
        if mtdt_data:
            title = mtdt_data.get("title", title)
            album_artist = mtdt_data.get("album_artist", album_artist)
            artist = mtdt_data.get("artist", album_artist)
            lyrics = mtdt_data.get("lyrics", lyrics)
            synced_lyrics = mtdt_data.get("synced_lyrics", synced_lyrics)
            ttml = mtdt_data.get("ttml", ttml)
            caption = mtdt_data.get("caption", caption)
            bpm = mtdt_data.get("bpm", bpm)
            keyscale = mtdt_data.get("keyscale", keyscale)
            timesignature = mtdt_data.get("timesignature", timesignature)
            language = mtdt_data.get("language", language)
            duration = mtdt_data.get("duration", duration)
            bpm = mtdt_data.get("bpm", bpm)
            bpm = mtdt_data.get("bpm", bpm)
            bpm = mtdt_data.get("bpm", bpm)

        # mutagenで音声ファイルのタグを読み取る
        if (not artist or not title) and MutagenFile is not None:
            audio = MutagenFile(file, easy=True)
            if audio is not None:
                title = (audio.get("title") or [""])[0]
                artist = (audio.get("artist") or [""])[0]
                album_artist = (audio.get("albumartist") or [""])[0]
        if album_artist and not artist:
            artist = album_artist

        default = cls(
            name=name,
            path=path,
            lyrics=lyrics,
            ttml=ttml,
            synced_lyrics=synced_lyrics,
            caption=caption,
            bpm=bpm,
            keyscale=keyscale,
            timesignature=timesignature,
            language=language,
            duration=duration,
            title=title,
            artist=artist,
            album_artist=album_artist,
        )

        return cls(
            name=name,
            path=path,
            lyrics=lyrics,
            ttml=ttml,
            synced_lyrics=synced_lyrics,
            caption=caption,
            bpm=bpm,
            keyscale=keyscale,
            timesignature=timesignature,
            language=language,
            duration=duration,
            title=title,
            artist=artist,
            album_artist=album_artist,
            is_expandable=False,
            default=default,
        )
