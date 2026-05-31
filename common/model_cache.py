from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CacheEntry:
    """キャッシュされた1モデルのエントリ。"""
    name: str
    value: Any
    _get_func: Callable
    _dispose_func: Callable
    cached: bool = True

    def dispose(self):
        """dispose_func を呼んでエントリをクリアする。"""
        if self.cached:
            self._dispose_func(self.value)
        self.cached = False
        self.name = ""
        self.value = None


class ModelCache:
    """ロード済みモデルのキャッシュ状態を管理するグローバルクラス。"""

    def __init__(self):
        self._entries: list[CacheEntry] = []

    def model_loaded(self, name: str, value: Any, get_func: Callable, dispose_func: Callable) -> CacheEntry:
        """モデルをキャッシュ済みとして登録する。既存エントリがあれば先に破棄する。"""
        existing = self._find(name)
        if existing and existing.cached:
            existing.dispose()
            self._entries.remove(existing)

        entry = CacheEntry(name=name, value=value, _get_func=get_func, _dispose_func=dispose_func)
        self._entries.append(entry)
        return entry

    def dispose(self, name: str):
        """指定名のモデルを破棄する。"""
        entry = self._find(name)
        if entry:
            entry.dispose()
            self._entries.remove(entry)

    def dispose_all(self):
        """全モデルを破棄する。"""
        for entry in list(self._entries):
            entry.dispose()
        self._entries.clear()

    def get_entry(self, name: str) -> CacheEntry | None:
        return self._find(name)

    @property
    def entries(self) -> list[CacheEntry]:
        return list(self._entries)

    def _find(self, name: str) -> CacheEntry | None:
        return next((e for e in self._entries if e.name == name), None)


model_cache = ModelCache()
