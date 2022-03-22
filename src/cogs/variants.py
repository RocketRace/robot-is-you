from __future__ import annotations
from dataclasses import dataclass

import re
from typing import TYPE_CHECKING, Any, Callable

from src.db import TileData

from .. import constants, errors
from ..tile import FullTile, Grid, RawTile, TileFields

if TYPE_CHECKING:
    from ...ROBOT import Bot

HandlerFn = Callable[['HandlerContext'], TileFields]
DefaultFn = Callable[['DefaultContext'], TileFields]

@dataclass
class ContextBase:
    '''The context that the (something) was invoked in.'''
    bot: Bot
    tile: RawTile
    grid: Grid[RawTile]
    position: tuple[int, int, int]
    grid_size: tuple[int, int]
    tile_data_cache: dict[str, TileData]
    flags: dict[str, Any]

    @property
    def tile_data(self) -> TileData | None:
        '''Associated tile data'''
        return self.tile_data_cache.get(self.tile.name)
    
    def is_adjacent(self, coordinate: tuple[int, int, int]) -> bool:
        '''Tile is next to a joining tile at this point in time.
        
        Coordinate format: (x, y, t)
        '''
        x, y, t = coordinate
        width, height = self.grid_size
        joining_tiles = (self.tile.name, "level")
        if x < 0 or y < 0 or y >= height or x >= width:
            return bool(self.flags.get("tile_borders"))
        if self.grid.get((x, y, t)) is None:
            return bool(self.flags.get("tile_borders"))
        return any(tile.name in joining_tiles for tile in self.grid[x, y, t])

@dataclass
class HandlerContext(ContextBase):
    '''The context that the handler was invoked in.'''
    fields: TileFields
    variant: str
    groups: tuple[str, ...]
    extras: dict[str, Any]
class DefaultContext(ContextBase):
    '''The context that a default factory was invoked in.'''

class VariantHandlers:
    def __init__(self, bot: Bot) -> None:
        self.handlers: list[Handler] = []
        self.bot = bot
        self.default_fields: DefaultFn = lambda ctx: {}
        self.tile_data_cache: dict[str, TileData] = {}

    def handler(
        self, 
        *, 
        pattern: str,
        variant_hints: dict[str, str],
        variant_group: str | None = None,
        order: int | None = None
    ) -> Callable[[HandlerFn], Handler]:
        '''Registers a variant handler.
        
        The decorated function should take one argument (`HandlerContext`) and return `TileFields`.

        The handler is invoked when the variant matches `pattern`. If the pattern includes any 
        capturing groups, they are accessible at `HandlerContext.groups`.

        `variant_hints` is a dict of (variant : user-friendly representation) pairs.
        Each variant should be valid for the handler. The representation should typically 
        be related to the variant provided, as it will be passed to the user. An empty
        dictionary should be passed to signify no hints.
        
        `variant_group` is a key used to group variant handlers together. It should
        be a user-friendly string. If set to None, the handlers are hidden.

        The lower `order` is, the earlier the handler is prioritized (loosely).
        If `order` is `None` (the default), the handler is given the least priority (loosely).
        '''
        def deco(fn: HandlerFn) -> Handler:
            handler = Handler(pattern, fn, variant_hints, variant_group)
            if order is None:
                self.handlers.append(handler)
            else:
                self.handlers.insert(order, handler)
            return handler
        return deco
    
    def default(self, fn: DefaultFn):
        '''Registers a default field factory.
        
        There can only be one factory.
        
        The function should take no arguments and return a `TileFields`.
        Successive calls to this decorator will replace previous factories.
        '''
        self.default_fields = fn
    
    def finalize(self, fn: Callable[[FullTile], None]):
        '''Registers a finalizer.
        
        There can only be one.
        '''
        self.finalizer = fn

    def all_variants(self) -> list[str]:
        '''All the possible variants
        
        tuples: (real string, representation string)
        '''
        return [
            repr
            for handler in self.handlers
            for repr in handler.hints.values()
        ]

    def valid_variants(self, tile: RawTile, grid: Grid[RawTile], tile_data_cache: dict[str, TileData]) -> dict[str, list[str]]:
        '''Returns the variants that are valid for a given tile.
        This data is pulled from the handler's `hints` attribute.
        
        The output is grouped by the variant group of the handler.
        '''
        out: dict[str, list[str]] = {}
        for handler in self.handlers:
            if handler.visible:
                for variant, repr in handler.hints.items():
                    try:
                        groups = handler.match(variant)
                        if groups is not None:
                            mock_ctx = HandlerContext(
                                bot=self.bot,
                                fields={},
                                groups=groups,
                                variant=variant,
                                tile=tile,
                                grid=grid,
                                position=(0, 0, 0),
                                extras={},
                                grid_size=(1,1), 
                                tile_data_cache=tile_data_cache,
                                flags=dict(disallow_custom_directions=True)
                            )
                            handler.handle(mock_ctx)
                    except errors.VariantError:
                        pass # Variant not possible
                    else:
                        out.setdefault(handler.group, []).append(repr)
        return out

    def handle_tile(
        self,
        tile: RawTile,
        grid: Grid[RawTile],
        position: tuple[int, int, int],
        grid_size: tuple[int, int],
        tile_data_cache: dict[str, TileData],
        **flags: Any
    ) -> FullTile:
        '''Take a RawTile and apply its variants to it'''
        default_ctx = DefaultContext(
            bot=self.bot,
            tile=tile,
            grid=grid,
            position=position,
            grid_size=grid_size,
            tile_data_cache=tile_data_cache,
            flags=flags
        )
        fields: TileFields = self.default_fields(default_ctx)
        extras = {}
        for variant in tile.variants:
            failed = True
            for handler in reversed(self.handlers):
                groups = handler.match(variant)
                if groups is not None:
                    failed = False
                    ctx = HandlerContext(
                        bot=self.bot,
                        fields=fields,
                        groups=groups,
                        variant=variant,
                        tile=tile,
                        grid=grid,
                        position=position,
                        extras=extras,
                        grid_size=grid_size,
                        tile_data_cache=tile_data_cache,
                        flags=flags
                    )
                    fields.update(handler.handle(ctx))
            if failed:
                raise errors.UnknownVariant(tile, variant)
        full = FullTile.from_tile_fields(tile, fields)
        self.finalizer(full, **flags)
        return full

    async def handle_grid(self, grid: Grid[RawTile], grid_size: tuple[int, int], **flags: Any) -> Grid[FullTile]:
        '''Apply variants to a full grid of raw tiles'''
        tile_data_cache = {
            data.name: data async for data in self.bot.db.tiles(
                set(tile.name for stack in grid.values() for tile in stack),
                maximum_version = flags.get("ignore_editor_overrides", 1000)
            )
        }
        return {
            index: [self.handle_tile(tile, grid, index, grid_size, tile_data_cache, **flags) for tile in stack]
            for index, stack in grid.items()
        }

class Handler:
    '''Handles a single variant'''
    def __init__(
        self,
        pattern: str,
        fn: HandlerFn,
        hints: dict[str, str],
        group: str | None
    ):
        self.pattern = pattern
        self.fn = fn
        self.hints = hints
        self.group = group

    @property
    def visible(self) -> bool:
        return self.group is not None

    def match(self, variant: str) -> tuple[str, ...] | None:
        '''Can this handler take the variant?
        
        Returns the matched groups if possible, else returns `None`.
        '''
        matches = re.fullmatch(self.pattern, variant)
        if matches is not None:
            return matches.groups()
    
    def handle(self, ctx: HandlerContext) -> TileFields:
        '''Handle the variant'''
        return self.fn(ctx)

def split_variant(variant: int | None) -> tuple[int, int]:
    '''The sleeping animation is slightly inconvenient'''
    if variant is None:
        return 0, 0
    dir, anim = divmod(variant, 8)
    if anim == 7:
        dir = (dir + 1) % 4
        anim = -1
    return dir * 8, anim

def join_variant(dir: int, anim: int) -> int:
    '''The sleeping animation is slightly inconvenient'''
    return (dir + anim) % 32

def setup(bot: Bot):
    '''Get the variant handler instance'''
    handlers = VariantHandlers(bot)
    bot.variant_handlers = handlers

    @handlers.default
    def default(ctx: DefaultContext) -> TileFields:
        '''Handles default colors, facing right, and auto-tiling'''
        if ctx.tile.name == "-":
            return {
                "empty": True
            }
        tile_data = ctx.tile_data
        color = (0, 3)
        variant = 0
        variant_fallback = 0
        if tile_data is not None:
            color = tile_data.active_color
            if tile_data.tiling in constants.AUTO_TILINGS:
                x, y, t = ctx.position
                # Only counts adjacent tiles, guaranteed to exist
                adj_right = ctx.is_adjacent((x + 1, y, t))
                adj_up = ctx.is_adjacent((x, y - 1, t))
                adj_left = ctx.is_adjacent((x - 1, y, t))
                adj_down = ctx.is_adjacent((x, y + 1, t))
                variant_fallback = constants.TILING_VARIANTS[(
                    adj_right, adj_up, adj_left, adj_down,
                    False, False, False, False
                )]
                # Variant with diagonal tiles as well, not guaranteed to exist
                # The renderer falls back to the simple variant if it doesn't
                adj_rightup = adj_right and adj_up and ctx.is_adjacent((x + 1, y - 1, t))
                adj_upleft = adj_up and adj_left and ctx.is_adjacent((x - 1, y - 1, t))
                adj_leftdown = adj_left and adj_down and ctx.is_adjacent((x - 1, y + 1, t))
                adj_downright = adj_down and adj_right and ctx.is_adjacent((x + 1, y + 1, t))
                variant = constants.TILING_VARIANTS.get((
                    adj_right, adj_up, adj_left, adj_down,
                    adj_rightup, adj_upleft, adj_leftdown, adj_downright
                ), variant_fallback)
            if ctx.flags.get("raw_output"):
                color = (0, 3)
            return {
                "variant_number": variant,
                "variant_fallback": variant_fallback,
                "color_index": color,
                "meta_level": 0,
                "sprite": (tile_data.source, tile_data.sprite),
            }
        if not ctx.tile.is_text:
            raise errors.TileNotFound(ctx.tile)
        return {
            "custom": True,
            "variant_number": variant,
            "color_index": color,
            "meta_level": 0,
        }

    @handlers.finalize
    def finalize(tile: FullTile, **flags) -> None:
        if flags.get("extra_names") is not None:
            name = tile.name.replace("/", "")
            variant = tile.variant_number
            meta_level = tile.meta_level
            flags["extra_names"].append(
                meta_level * "meta_" + name
            )
        if tile.custom and tile.custom_style is None:
            if len(tile.name[5:]) == 2 and flags.get("default_to_letters"):
                tile.custom_style = "letter"
            else:
                tile.custom_style = "noun"

    @handlers.handler(
        pattern=r"|".join(constants.DIRECTION_VARIANTS),
        variant_hints=constants.DIRECTION_REPRESENTATION_VARIANTS,
        variant_group="Alternate sprites"
    )
    def directions(ctx: HandlerContext) -> TileFields:
        dir = constants.DIRECTION_VARIANTS[ctx.variant]
        _, anim = split_variant(ctx.fields.get("variant_number"))
        tile_data = ctx.tile_data
        if tile_data is not None and tile_data.tiling in constants.DIRECTION_TILINGS:
            return {
                "variant_number": join_variant(dir, anim),
                "custom_direction": dir
            }
        elif ctx.flags.get("ignore_bad_directions"):
            return {}
        else:
            if ctx.flags.get("disallow_custom_directions") and not ctx.tile.is_text:
                raise errors.BadTilingVariant(ctx.tile, ctx.variant, "<missing>")
            return {
                "custom_direction": dir
            }

    @handlers.handler(
        pattern=r"|".join(constants.SOFT_DIRECTION_VARIANTS),
        variant_hints={},
    )
    def soft_directions(ctx: HandlerContext) -> TileFields:
        dir = constants.SOFT_DIRECTION_VARIANTS[ctx.variant]
        _, anim = split_variant(ctx.fields.get("variant_number"))
        tile_data = ctx.tile_data
        if tile_data is not None and tile_data.tiling in constants.DIRECTION_TILINGS:
            return {
                "variant_number": join_variant(dir, anim),
            }
        return {}


    @handlers.handler(
        pattern=r"|".join(constants.ANIMATION_VARIANTS),
        variant_hints=constants.ANIMATION_REPRESENTATION_VARIANTS,
        variant_group="Alternate sprites"
    )
    def animations(ctx: HandlerContext) -> TileFields:
        anim = constants.ANIMATION_VARIANTS[ctx.variant]
        dir, _ = split_variant(ctx.fields.get("variant_number"))
        tile_data = ctx.tile_data
        tiling = None
        if tile_data is not None:
            tiling = tile_data.tiling
            if tiling in constants.ANIMATION_TILINGS:
                return {
                    "variant_number": join_variant(dir, anim)
                }
        raise errors.BadTilingVariant(ctx.tile.name, ctx.variant, tiling)
    
    @handlers.handler(
        pattern=r"|".join(constants.SOFT_ANIMATION_VARIANTS),
        variant_hints={},
    )
    def soft_animations(ctx: HandlerContext) -> TileFields:
        anim = constants.SOFT_ANIMATION_VARIANTS[ctx.variant]
        dir, _ = split_variant(ctx.fields.get("variant_number"))
        tile_data = ctx.tile_data
        tiling = None
        if tile_data is not None:
            tiling = tile_data.tiling
            if tiling in constants.ANIMATION_TILINGS:
                return {
                    "variant_number": join_variant(dir, anim)
                }
        return {}
    
    @handlers.handler(
        pattern=r"|".join(constants.SLEEP_VARIANTS),
        variant_hints=constants.SLEEP_REPRESENTATION_VARIANTS,
        variant_group="Alternate sprites"
    )
    def sleep(ctx: HandlerContext) -> TileFields:
        anim = constants.SLEEP_VARIANTS[ctx.variant]
        dir, _ = split_variant(ctx.fields.get("variant_number"))
        tile_data = ctx.tile_data
        if tile_data is not None:
            if tile_data.tiling in constants.SLEEP_TILINGS:
                return {
                    "variant_number": join_variant(dir, anim)
                }
            raise errors.BadTilingVariant(ctx.tile.name, ctx.variant, tile_data.tiling)
        raise errors.BadTilingVariant(ctx.tile.name, ctx.variant, "<missing>")

    @handlers.handler(
        pattern=r"|".join(constants.SOFT_SLEEP_VARIANTS),
        variant_hints={},
    )
    def soft_sleep(ctx: HandlerContext) -> TileFields:
        anim = constants.SOFT_SLEEP_VARIANTS[ctx.variant]
        dir, _ = split_variant(ctx.fields.get("variant_number"))
        tile_data = ctx.tile_data
        if tile_data is not None:
            if tile_data.tiling in constants.SLEEP_TILINGS:
                return {
                    "variant_number": join_variant(dir, anim)
                }
        return {}

    @handlers.handler(
        pattern=r"|".join(constants.AUTO_VARIANTS),
        variant_hints=constants.AUTO_REPRESENTATION_VARIANTS,
        variant_group="Alternate sprites"
    )
    def auto(ctx: HandlerContext) -> TileFields:
        tile_data = ctx.tile_data
        tiling = None
        if tile_data is not None:
            tiling = tile_data.tiling
            if tiling in constants.AUTO_TILINGS:
                if ctx.extras.get("auto_override", False):
                    num = ctx.fields.get("variant_number") or 0
                    return {
                        "variant_number": num | constants.AUTO_VARIANTS[ctx.variant]
                    }
                else:
                    ctx.extras["auto_override"] = True
                    return {
                        "variant_number": constants.AUTO_VARIANTS[ctx.variant]
                    }
        raise errors.BadTilingVariant(ctx.tile.name, ctx.variant, tiling)

    @handlers.handler(
        pattern=r"|".join(constants.SOFT_AUTO_VARIANTS),
        variant_hints={},
    )
    def soft_auto(ctx: HandlerContext) -> TileFields:
        tile_data = ctx.tile_data
        tiling = None
        if tile_data is not None:
            tiling = tile_data.tiling
            if tiling in constants.AUTO_TILINGS:
                if ctx.extras.get("auto_override", False):
                    num = ctx.fields.get("variant_number") or 0
                    return {
                        "variant_number": num | constants.SOFT_AUTO_VARIANTS[ctx.variant]
                    }
                else:
                    ctx.extras["auto_override"] = True
                    return {
                        "variant_number": constants.SOFT_AUTO_VARIANTS[ctx.variant]
                    }
        return {}

    @handlers.handler(
        pattern=r"\d{1,2}",
        variant_hints={"0": "`raw variant number` (e.g. `8`, `17`, `31`)"},
        variant_group="Alternate sprites"
    )
    def raw_variant(ctx: HandlerContext) -> TileFields:
        variant = int(ctx.variant)
        tile_data = ctx.tile_data
        if tile_data is None:
            raise errors.TileDoesntExist(ctx.tile.name, ctx.variant)
        tiling = tile_data.tiling

        if tiling in constants.AUTO_TILINGS:
            if variant >= 16:
                raise errors.BadTilingVariant(ctx.tile.name, ctx.variant, tiling)
        else:
            dir, anim = split_variant(variant)
            if dir != 0:
                if tiling not in constants.DIRECTION_TILINGS or dir not in constants.DIRECTIONS:
                    raise errors.BadTilingVariant(ctx.tile.name, ctx.variant, tiling)
            if anim != 0:
                if anim in constants.SLEEP_VARIANTS.values():
                    if tiling not in constants.SLEEP_TILINGS:
                        raise errors.BadTilingVariant(ctx.tile.name, ctx.variant, tiling)
                else:
                    if tiling not in constants.ANIMATION_TILINGS or anim not in constants.ANIMATION_VARIANTS.values():
                        raise errors.BadTilingVariant(ctx.tile.name, ctx.variant, tiling)
        return {
            "variant_number": variant
        }

    @handlers.handler(
        pattern=r"|".join(constants.COLOR_NAMES),
        variant_hints=constants.COLOR_REPRESENTATION_VARIANTS,
        variant_group="Colors"
    )
    def color_name(ctx: HandlerContext) -> TileFields:
        return {
            "color_index": constants.COLOR_NAMES[ctx.variant]
        }

    @handlers.handler(
        pattern=r"(\d)/(\d)",
        variant_hints={"0/0": "`palette_x/palette_y` (Color palette index, e.g. `0/3`)"},
        variant_group="Colors"
    )
    def color_index(ctx: HandlerContext) -> TileFields:
        x, y = int(ctx.groups[0]), int(ctx.groups[1])
        if x > 6 or y > 4:
            raise errors.BadPaletteIndex(ctx.tile.name, ctx.variant)
        return {
            "color_index": (int(ctx.groups[0]), int(ctx.groups[1]))
        }
    
    @handlers.handler(
        pattern=r"#([0-9a-fA-F]{1,6})",
        variant_hints={"#ffffff": "`#hex_code` (Color hex code, e.g. `#f055ee`)"},
        variant_group="Colors"
    )
    def color_rgb(ctx: HandlerContext) -> TileFields:
        color = int(ctx.groups[0], base=16)
        red = color >> 16
        green = (color & 0x00ff00) >> 8
        blue = color & 0x0000ff
        return {
            "color_rgb": (red, green, blue)
        }

    @handlers.handler(
        pattern=r"inactive|in",
        variant_hints={"in": "`inactive` / `in` (Inactive text color)"},
        variant_group="Colors"
    )
    def inactive(ctx: HandlerContext) -> TileFields:
        color = ctx.fields.get("color_index", (0, 3))
        tile_data = ctx.tile_data
        if tile_data is not None and ctx.tile.is_text:
            # only the first `:inactive` should pick the provided color
            if color == tile_data.active_color:
                return {
                    "color_index": tile_data.inactive_color
                }
        return {
            "color_index": constants.INACTIVE_COLORS[color]
        }

    @handlers.handler(
        pattern=r"hide",
        variant_hints={"hide": "`hide` (It's a mystery)"},
        variant_group="Filters"
    )
    def hide(ctx: HandlerContext) -> TileFields:
        return {
            "empty": True
        }

    @handlers.handler(
        pattern=r"meta|m",
        variant_hints={"m": "`meta` / `m` (+1 meta layer)"},
        variant_group="Filters"
    )
    def meta(ctx: HandlerContext) -> TileFields:
        level = ctx.fields.get("meta_level", 0)
        if level >= constants.MAX_META_DEPTH:
            raise errors.BadMetaVariant(ctx.tile.name, ctx.variant, level)
        return {
            "meta_level": level + 1
        }
    
    @handlers.handler(
        pattern=r"m(\d)",
        variant_hints={"m1": "`mX` (A specific meta depth, e.g. `m1`, `m3`)"},
        variant_group="Filters"
    )
    def meta_absolute(ctx: HandlerContext) -> TileFields:
        level = int(ctx.groups[0])
        if level > constants.MAX_META_DEPTH:
            raise errors.BadMetaVariant(ctx.tile.name, ctx.variant, level)
        return {
            "meta_level": level
        }

    @handlers.handler(
        pattern=r"noun",
        variant_hints={"noun": "`noun` (Noun-style text)"},
        variant_group="Custom text"
    )
    def noun(ctx: HandlerContext) -> TileFields:
        if not ctx.tile.is_text:
            raise errors.TileNotText(ctx.tile.name, "noun")
        tile_data = ctx.tile_data
        if tile_data is not None:
            if constants.TEXT_TYPES[tile_data.text_type] == "property":
                return {
                    "style_flip": True,
                    "custom_style": "noun"
                }
        return {
            "custom": True,
            "custom_style": "noun"
        }
    
    @handlers.handler(
        pattern=r"letter|let",
        variant_hints={"let": "`letter` / `let` (Letter-style text)"},
        variant_group="Custom text"
    )
    def letter(ctx: HandlerContext) -> TileFields:
        if not ctx.tile.is_text:
            raise errors.TileNotText(ctx.tile.name, "letter")
        if len(ctx.tile.name[5:]) > 2:
            raise errors.BadLetterVariant(ctx.tile.name, "letter")
        return {
            "custom": True,
            "custom_style": "letter"
        }
    
    @handlers.handler(
        pattern=r"property|prop",
        variant_hints={"prop": "`property` / `prop` (Property-style text)"},
        variant_group="Custom text"
    )
    def property(ctx: HandlerContext) -> TileFields:
        tile_data = ctx.tile_data
        if not ctx.tile.is_text:
            if tile_data is not None:
                # this will be funny
                return {
                    "style_flip": True,
                    "custom_style": "property"
                }
            else:
                raise errors.TileDoesntExist(ctx.tile.name, ctx.variant)
        if tile_data is not None:
            if constants.TEXT_TYPES[tile_data.text_type] == "noun":
                return {
                    "style_flip": True,
                    "custom_style": "property"
                }
        return {
            "custom_style": "property",
            "custom": True,
        }
    @handlers.handler(
        pattern=r"nothing",
        variant_hints={"nothing": "`nothing` (Do nothing)"},
        variant_group="Filters"
    )
    def nothing(ctx: HandlerContext) -> TileFields:
        return {}

    @handlers.handler(
        pattern="mask",
        variant_hints={"mask": "`mask` (Mask with this sprite outline)"},
        variant_group="Filters"
    )
    def mask(ctx: HandlerContext) -> TileFields:
        return {"mask_alpha": True}

    @handlers.handler(
        pattern="cut",
        variant_hints={"cut": "`cut` (Cut this sprite outline)"},
        variant_group="Filters"
    )
    def cut(ctx: HandlerContext) -> TileFields:
        return {"cut_alpha": True}

    @handlers.handler(
        pattern="face",
        variant_hints={"face": "`face` (Pick out the details in a sprite)"},
        variant_group="Filters"
    )
    def face(ctx: HandlerContext) -> TileFields:
        return {"face": True}
    
    @handlers.handler(
        pattern="blank",
        variant_hints={"blank": "`blank` (Pick out the shape of the sprite)"},
        variant_group="Filters"
    )
    def blank(ctx: HandlerContext) -> TileFields:
        return {"blank": True}

    return handlers
