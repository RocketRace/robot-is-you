from __future__ import annotations

import re
from ..types import Bot
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..tile import FullGrid, GridIndex, RawGrid

from ..tile import FullTile, RawTile, TileFields
from .. import constants, errors

HandlerFn = Callable[['HandlerContext'], TileFields]
DefaultFn = Callable[['DefaultContext'], TileFields]

class ContextBase:
    '''The context that the (something) was invoked in.'''
    def __init__(self, *, bot: Bot, tile: RawTile, grid: RawGrid, index: GridIndex, **flags: Any) -> None:
        self.bot = bot
        self.tile = tile
        self.grid = grid
        self.index = index
        self.flags = flags

    @property
    def tile_data(self) -> dict | None:
        '''Associated tile data'''
        if self.flags.get("ignore_editor_overrides"):
            override = self.bot.get.level_tile_data(self.tile.name)
            if override is not None:
                return override
        return self.bot.get.tile_data(self.tile.name)
    
    def is_adjacent(self, coordinate: tuple[int, int],) -> bool:
        '''Tile is next to a joining tile'''
        x, y = coordinate
        joining_tiles = (self.tile.name, "level")
        if x < 0 or y < 0 or y >= len(self.grid) or x >= len(self.grid[0]):
            return bool(self.flags.get("tile_borders"))
        return any(t.name in joining_tiles for t in self.grid[y][x])

class HandlerContext(ContextBase):
    '''The context that the handler was invoked in.'''
    def __init__(self, *, 
        fields: TileFields,
        variant: str,
        groups: tuple[str, ...],
        extras: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        self.fields = fields
        self.variant = variant
        self.groups = groups
        self.extras = extras
        super().__init__(**kwargs)

class DefaultContext(ContextBase):
    '''The context that a default factory was invoked in.'''

class VariantHandlers:
    def __init__(self, bot: Bot) -> None:
        self.handlers: list[Handler] = []
        self.bot = bot
        self.default_fields: DefaultFn = lambda ctx: {}

    def handler(self, *, pattern: str, order: int | None = None) -> Callable[[HandlerFn], Handler]:
        '''Registers a variant handler.
        
        The decorated function should take one argument (`HandlerContext`) and return `TileFields`.

        The handler is invoked when the variant matches `pattern`. If the pattern includes any 
        capturing groups, they are accessible at `HandlerContext.groups`.

        The lower `order` is, the earlier the handler is prioritized (loosely).
        If `order` is `None` or not given, the handler is given the least priority (loosely).
        '''
        def deco(fn: HandlerFn) -> Handler:
            handler = Handler(pattern, fn)
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
    
    def handle_tile(self, tile: RawTile, grid: RawGrid, index: GridIndex, **flags: Any) -> FullTile:
        '''Take a RawTile and apply its variants to it'''
        default_ctx = DefaultContext(
            bot=self.bot,
            tile=tile,
            grid=grid,
            index=index,
            **flags
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
                        index=index,
                        extras=extras,
                        **flags
                    )
                    fields.update(handler.handle(ctx))
            if failed:
                raise errors.UnknownVariant(tile, variant)
        return FullTile.from_tile_fields(tile, fields)
    
    def handle_grid(self, grid: RawGrid, **flags: Any) -> FullGrid:
        '''Apply variants to a full grid of raw tiles'''
        return [
            [
                [
                    self.handle_tile(tile, grid, (x, y, z), **flags)
                    for z, tile in enumerate(stack)
                ]
                for x, stack in enumerate(row)
            ]
            for y, row in enumerate(grid)
        ]

class Handler:
    '''Handles a single variant'''
    def __init__(self, pattern: str, fn: HandlerFn):
        self.pattern = pattern
        self.fn = fn

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
        dir = (dir + 1) % 8
        anim = -1
    return dir * 8, anim

def join_variant(dir: int, anim: int) -> int:
    '''The sleeping animation is slightly inconvenient'''
    return (dir + anim) % 32

def setup(bot: Bot):
    '''Get the variant handler instance'''
    handlers = VariantHandlers(bot)
    bot.handlers = handlers

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
        if tile_data is not None:
            if tile_data.get("active") is not None:
                color = (int(tile_data["active"][0]), int(tile_data["active"][1]))
            elif tile_data.get("color") is not None:
                color = (int(tile_data["color"][0]), int(tile_data["color"][1]))
            if tile_data["tiling"] in constants.AUTO_TILINGS:
                x, y, _ = ctx.index
                variant = (
                    + 1 * ctx.is_adjacent((x + 1, y))
                    + 2 * ctx.is_adjacent((x, y - 1))
                    + 4 * ctx.is_adjacent((x - 1, y))
                    + 8 * ctx.is_adjacent((x, y + 1))
                )
            return {
                "custom_style": constants.TEXT_STYLES[tile_data.get("type", "0")], # type:ignore
                "variant_number": variant,
                "color_index": color,
                "meta_level": 0,
                "sprite": (tile_data["source"], tile_data["sprite"]),
            }
        if not ctx.tile.is_text:
            raise errors.TileNotFound(ctx.tile)
        return {
            "custom": True,
            "custom_style": "noun",
            "variant_number": variant,
            "color_index": color,
            "meta_level": 0,
        }

    @handlers.handler(pattern=r"|".join(constants.DIRECTION_VARIANTS))
    def directions(ctx: HandlerContext) -> TileFields:
        dir = constants.DIRECTION_VARIANTS[ctx.variant]
        _, anim = split_variant(ctx.fields.get("variant_number"))
        tile_data = ctx.tile_data
        if tile_data is not None and tile_data["tiling"] in constants.DIRECTION_TILINGS:
            return {
                "variant_number": join_variant(dir, anim),
                "custom_direction": dir
            }
        elif ctx.flags.get("ignore_bad_directions"):
            return {}
        else:
            return {
                "custom_direction": dir
            }

    @handlers.handler(pattern=r"|".join(constants.ANIMATION_VARIANTS))
    def animations(ctx: HandlerContext) -> TileFields:
        anim = constants.ANIMATION_VARIANTS[ctx.variant]
        dir, _ = split_variant(ctx.fields.get("variant_number"))
        tile_data = ctx.tile_data
        tiling = None
        if tile_data is not None:
            tiling = tile_data["tiling"]
            if tiling in constants.ANIMATION_TILINGS:
                return {
                    "variant_number": join_variant(dir, anim)
                }
        raise errors.BadTilingVariant(ctx.tile.name, tiling, ctx.variant)
    
    @handlers.handler(pattern=r"|".join(constants.SLEEP_VARIANTS))
    def sleep(ctx: HandlerContext) -> TileFields:
        anim = constants.SLEEP_VARIANTS[ctx.variant]
        dir, _ = split_variant(ctx.fields.get("variant_number"))
        tile_data = ctx.tile_data
        tiling = None
        if tile_data is not None and tile_data["tiling"] in constants.SLEEP_TILINGS:
            tiling = tile_data["tiling"]
            if tiling in constants.SLEEP_TILINGS:
                return {
                    "variant_number": join_variant(dir, anim)
                }
        raise errors.BadTilingVariant(ctx.tile.name, tiling, ctx.variant)

    @handlers.handler(pattern=r"|".join(constants.AUTO_VARIANTS))
    def auto(ctx: HandlerContext) -> TileFields:
        tile_data = ctx.tile_data
        tiling = None
        if tile_data is not None:
            tiling = tile_data["tiling"]
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
        raise errors.BadTilingVariant(ctx.tile.name, tiling, ctx.variant)

    @handlers.handler(pattern=r"\d{1,2}")
    def raw_variant(ctx: HandlerContext) -> TileFields:
        variant = int(ctx.variant)
        tile_data = ctx.tile_data
        if tile_data is None:
            raise ValueError("what tile is that even")
        tiling = tile_data["tiling"]

        if tiling in constants.AUTO_TILINGS:
            if variant >= 16:
                raise errors.BadTilingVariant(ctx.tile.name, tiling, ctx.variant)
        else:
            dir, anim = split_variant(variant)
            if dir != 0:
                if tiling not in constants.DIRECTION_TILINGS:
                    raise errors.BadTilingVariant(ctx.tile.name, tiling, ctx.variant)
            if anim != 0:
                if anim in constants.SLEEP_VARIANTS.values():
                    if tiling not in constants.SLEEP_TILINGS:
                        raise errors.BadTilingVariant(ctx.tile.name, tiling, ctx.variant)
                else:
                    if tiling not in constants.ANIMATION_TILINGS:
                        raise errors.BadTilingVariant(ctx.tile.name, tiling, ctx.variant)
        return {
            "variant_number": variant
        }

    @handlers.handler(pattern=r"|".join(constants.COLOR_NAMES))
    def color_name(ctx: HandlerContext) -> TileFields:
        return {
            "color_index": constants.COLOR_NAMES[ctx.variant]
        }

    @handlers.handler(pattern=r"(\d)/(\d)")
    def color_index(ctx: HandlerContext) -> TileFields:
        x, y = int(ctx.groups[0]), int(ctx.groups[1])
        if x > 6 or y > 4:
            raise errors.BadPaletteIndex(ctx.tile.name, ctx.variant)
        return {
            "color_index": (int(ctx.groups[0]), int(ctx.groups[1]))
        }
    
    @handlers.handler(pattern=r"#([0-9a-fA-F]{1,6})")
    def color_rgb(ctx: HandlerContext) -> TileFields:
        color = int(ctx.groups[0], base=16)
        red = color >> 16
        green = (color | 0x00ff00) >> 8
        blue = color | 0x0000ff
        return {
            "color_rgb": (red, green, blue)
        }

    @handlers.handler(pattern=r"inactive|in")
    def inactive(ctx: HandlerContext) -> TileFields:
        color = ctx.fields.get("color_index", (0, 3))
        tile_data = ctx.tile_data
        if tile_data is not None and tile_data.get("active") is not None:
            # only the first `:inactive` should pick the provided color
            if color == tile_data["active"]:
                return {
                    "color_index": tile_data["color"]
                }
        return {
            "color_index": constants.INACTIVE_COLORS[color]
        }

    @handlers.handler(pattern=r"hide")
    def hide(ctx: HandlerContext) -> TileFields:
        return {
            "empty": True
        }

    @handlers.handler(pattern=r"meta|m")
    def meta(ctx: HandlerContext) -> TileFields:
        level = ctx.fields.get("meta_level", 0)
        if level >= constants.MAX_META_DEPTH:
            raise errors.BadMetaVariant(ctx.tile.name, ctx.variant, level)
        return {
            "meta_level": level + 1
        }
    
    @handlers.handler(pattern=r"m(\d)")
    def meta_absolute(ctx: HandlerContext) -> TileFields:
        level = int(ctx.groups[0])
        if level > constants.MAX_META_DEPTH:
            raise errors.BadMetaVariant(ctx.tile.name, ctx.variant, level)
        return {
            "meta_level": level
        }

    @handlers.handler(pattern=r"noun")
    def noun(ctx: HandlerContext) -> TileFields:
        if not ctx.tile.is_text:
            raise errors.TileNotText(ctx.tile.name, "noun")
        tile_data = ctx.tile_data
        if tile_data is not None:
            if constants.TEXT_STYLES[tile_data["type"]] == "property":
                return {
                    "style_flip": True,
                    "custom_style": "noun"
                }
        return {
            "custom": True,
            "custom_style": "noun"
        }
    
    @handlers.handler(pattern=r"letter|let")
    def letter(ctx: HandlerContext) -> TileFields:
        if not ctx.tile.is_text:
            raise errors.TileNotText(ctx.tile.name, "letter")
        if len(ctx.tile.name[5:]) > 2:
            raise errors.BadLetterVariant(ctx.tile.name, "letter")
        return {
            "custom": True,
            "custom_style": "letter"
        }
    
    @handlers.handler(pattern=r"property|prop")
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
                raise ValueError("yet again (but this time on a technicality)")
        if tile_data is not None:
            if constants.TEXT_STYLES[tile_data["type"]] == "noun":
                return {
                    "style_flip": True,
                    "custom_style": "property"
                }
        return {
            "custom_style": "property",
            "custom": True,
        }

    return handlers
