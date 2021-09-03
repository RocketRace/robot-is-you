from __future__ import annotations

from dataclasses import dataclass
from src.constants import BABA_WORLD
from typing import TYPE_CHECKING, Literal, TypedDict

from PIL import Image

from . import errors

if TYPE_CHECKING:
    RawGrid = list[list[list['RawTile']]]
    FullGrid = list[list[list['FullTile']]]
    GridIndex = tuple[int, int, int]

@dataclass
class Positioned:
    '''Has a position, that's it'''
    position: tuple[int, int, int, int]

@dataclass
class SkeletonTile:
    '''Name, that's all'''
    name: str

    def __repr__(self) -> str:
        return self.name
    
    @property
    def is_empty(self) -> bool:
        '''Text is blank'''
        return self.name == "-" or self.name == "text_-"
    
    @property
    def is_previous(self) -> bool:
        '''Text is the previous repetition tile'''
        return self.name == "_"

    @property
    def is_text(self) -> bool:
        '''Text is special'''
        return self.name.startswith("text_")

@dataclass
class RawTile(SkeletonTile):
    '''Raw tile given from initial pass of +rule and +tile command parsing'''
    variants: list[str]

    @classmethod
    def from_str(cls, string: str) -> RawTile:
        '''Parse from user input'''
        parts = string.split(":")
        if len(parts[0]) == 0:
            raise errors.EmptyTile()
        if any(len(part) == 0 for part in parts):
            raise errors.EmptyVariant(parts[0])
        return RawTile(parts[0], parts[1:])

@dataclass
class PositionedTile(Positioned, RawTile): # bases must be in this order
    @classmethod
    def blank(cls, position: tuple[int, int, int, int]) -> PositionedTile:
        '''z to undo, r to reset'''
        return PositionedTile("-", [], position)

    @classmethod
    def from_raw(cls, raw: RawTile, position: tuple[int, int, int, int]) -> PositionedTile:
        '''Upgrades the raw tile.'''
        return cls(
            raw.name,
            raw.variants,
            position,
        )

    def reposition(self, position: tuple[int, int, int, int]) -> PositionedTile:
        '''Move across space / time'''
        return type(self)(
            self.name,
            self.variants.copy(),
            position,
        )

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

@dataclass
class FullTile(Positioned, SkeletonTile): # note order of bases
    '''A tile ready to be rendered'''
    sprite: tuple[str, str] = BABA_WORLD, "error"
    variant_number: int = 0
    color_index: tuple[int, int] = (0, 3)
    color_rgb: tuple[int, int, int] | None = None
    custom: bool = False
    style_flip: bool = False
    empty: bool = False
    meta_level: int = 0
    custom_direction: int | None = None
    custom_style: Literal["noun", "property", "letter"] | None = None
    
    @classmethod
    def from_tile_fields(cls, tile: PositionedTile, fields: TileFields) -> FullTile:
        '''Create a FullTile from a RawTile and TileFields'''
        return FullTile(
            tile.name,
            tile.position,
            **fields
        )

@dataclass
class ReadyTile(Positioned):
    '''Tile that's about to be rendered, and already has a prerendered sprite.'''
    frames: tuple[Image.Image, Image.Image, Image.Image] | None
