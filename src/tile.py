from __future__ import annotations
from typing import Literal, TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    RawGrid = list[list[list['RawTile']]]
    FullGrid = list[list[list['FullTile']]]
    GridIndex = tuple[int, int, int]

class RawTile:
    '''Raw tile given from +rule and +tile commands'''
    def __init__(self, name: str, variants: list[str]) -> None:
        self.name = name
        self.variants = variants
    
    @classmethod
    def from_str(cls, string: str) -> RawTile:
        '''Parse from user input'''
        parts = string.split(":")
        if len(parts[0]) == 0:
            raise ValueError("Empty tile name not allowed")
        if any(len(part) == 0 for part in parts):
            raise ValueError("Empty variant not allowed")
        return RawTile(parts[0], parts[1:])
    
    @property
    def is_text(self) -> bool:
        return self.name.startswith("text_")

class TileFields(TypedDict, total=False):
    auto_override: bool
    variant_number: int
    color_index: tuple[int, int]
    empty: bool
    meta_level: int
    generate: bool
    custom_direction: int
    custom_style: str

class FullTile:
    def __init__(self, *,
        name: str,
        variant_number: int,
        color_index: tuple[int, int],
        empty: bool = False,
        meta_level: int = 0,
        generate: bool = False,
        custom_direction: int | None = None,
        custom_style: str | None = None,
    ) -> None:
        self.name = name
        self.variant_number = variant_number
        self.color_index = color_index
        self.empty = empty
        self.meta_level = meta_level
        self.generate = generate
        self.custom_direction = custom_direction
        self.custom_style = custom_style

    @classmethod
    def from_tile_fields(cls, tile: RawTile, fields: TileFields) -> FullTile:
        '''Create a FullTile from a RawTile and TileFields'''
        fields.pop("auto_override")
        return FullTile(
            name=tile.name,
            **fields # type: ignore
        )