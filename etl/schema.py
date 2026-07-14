from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecipeIR:
    id: int
    source: str
    title: str
    minutes: int
    tags: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    ingredients: list[str] = field(default_factory=list)
    n_ingredients: int = 0
    calories: float | None = None
    rating_mean: float | None = None
    rating_n: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "RecipeIR":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})
