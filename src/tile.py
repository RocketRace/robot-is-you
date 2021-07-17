from __future__ import annotations
from typing import Literal, TYPE_CHECKING, TypedDict
from . import errors

if TYPE_CHECKING:
    RawGrid = list[list[list['RawTile']]]
    FullGrid = list[list[list['FullTile']]]
    GridIndex = tuple[int, int, int]

class RawTile:
    '''Raw tile given from initial pass of +rule and +tile command parsing'''
    def __init__(self, name: str, variants: list[str]) -> None:
        self.name = name
        self.variants = variants
    
    def __repr__(self) -> str:
        return self.name
    
    @classmethod
    def from_str(cls, string: str) -> RawTile:
        '''Parse from user input'''
        parts = string.split(":")
        if len(parts[0]) == 0:
            raise errors.EmptyTile()
        if any(len(part) == 0 for part in parts):
            raise errors.EmptyVariant(parts[0])
        return RawTile(parts[0], parts[1:])
    
    @property
    def is_text(self) -> bool:
        '''Text is special'''
        return self.name.startswith("text_")

class TileFields(TypedDict, total=False):
    sprite: tuple[str, str]
    variant_number: int
    color_index: tuple[int, int]
    color_rgb: tuple[int, int, int]
    empty: bool
    meta_level: int
    custom_direction: int
    custom_style: Literal["noun", "property", "letter"]
    custom: bool
    style_flip: bool

class FullTile:
    '''A tile ready to be rendered'''
    def __init__(self, *,
        name: str,
        sprite: tuple[str, str] | None = None, 
        variant_number: int | None = None,
        color_index: tuple[int, int] | None = None,
        color_rgb: tuple[int, int, int] | None = None,
        custom: bool = False,
        style_flip: bool = False,
        empty: bool = False,
        meta_level: int = 0,
        custom_direction: int | None = None,
        custom_style: Literal["noun", "property", "letter"] | None = None,
    ) -> None:
        self.name = name
        self.sprite = sprite
        self.variant_number = variant_number
        self.color_index = color_index
        self.color_rgb = color_rgb
        self.empty = empty
        self.meta_level = meta_level
        self.style_flip = style_flip
        self.custom = custom
        self.custom_direction = custom_direction
        self.custom_style = custom_style

    @classmethod
    def from_tile_fields(cls, tile: RawTile, fields: TileFields) -> FullTile:
        '''Create a FullTile from a RawTile and TileFields'''
        return FullTile(
            name=tile.name,
            **fields
        )
