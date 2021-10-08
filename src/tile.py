from __future__ import annotations

from dataclasses import dataclass
from src.constants import BABA_WORLD
from typing import TYPE_CHECKING, Literal, TypeVar, TypedDict

from PIL import Image

from . import errors

if TYPE_CHECKING:
    _T = TypeVar("_T")
    Grid = dict[tuple[int, int, int], list[_T]]

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
    ephemeral: bool = False
    moved: bool = False

    @classmethod
    def from_str(cls, string: str, ephemeral: bool = False, moved: bool = False) -> RawTile:
        '''Parse from user input'''
        parts = string.split(":")
        if len(parts[0]) == 0:
            raise errors.EmptyTile()
        if any(len(part) == 0 for part in parts):
            raise errors.EmptyVariant(parts[0])
        return RawTile(parts[0], parts[1:], ephemeral)

    def copy(self) -> RawTile:
        return RawTile(
            self.name, self.variants.copy(), self.ephemeral
        )

    @classmethod
    def blank(cls) -> RawTile:
        '''z to undo, r to reset'''
        return RawTile("-", [], False)

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
    mask_alpha: bool
    cut_alpha: bool
    face: bool
    blank: bool

@dataclass
class FullTile(SkeletonTile):
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
    mask_alpha: bool = False
    cut_alpha: bool = False
    face: bool = False
    blank: bool = False
    
    @classmethod
    def from_tile_fields(cls, tile: RawTile, fields: TileFields) -> FullTile:
        '''Create a FullTile from a RawTile and TileFields'''
        return FullTile(
            tile.name,
            **fields
        )

@dataclass
class ReadyTile:
    '''Tile that's about to be rendered, and already has a prerendered sprite.'''
    frames: tuple[Image.Image, Image.Image, Image.Image] | None
    mask_alpha: bool = False
    cut_alpha: bool = False
