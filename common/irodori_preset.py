import dataclasses


@dataclasses.dataclass
class IrodoriPreset:
    """推論セクションのオプション設定1件分。"""
    name: str = ""
    text: str = ""
    lora_adapter: list[str] = dataclasses.field(default_factory=list)
    lora_scale: float = 1.0
    mixed_ref_enabled: bool = False
    ref_embed_a: str | None = None
    ref_embed_b: str | None = None
    ratio_a: float = 0.5
    ref_embed_method: str = "linear"
    voices: list[str] = dataclasses.field(default_factory=list)
    cfg_scale_text: float = 3.0
    cfg_scale_speaker: float = 5.0
    num_steps: int = 40
    response_format: str = "wav"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "IrodoriPreset":
        """未知キーを無視して復元。将来フィールドが追加されても旧 JSON を読める。"""
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})
