from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

from ..tile import PositionedTile

if TYPE_CHECKING:
    from ...ROBOT import Bot
    MacroFn = Callable[[list[PositionedTile], PositionedTile, tuple[str, ...]], tuple[int, int, int, int]]

class OperationMacros:
    def __init__(self, bot: Bot) -> None:
        self.macros: list[Macro] = []
        self.bot = bot

    def macro(
        self, 
        *, 
        pattern: str,
        operation_hints: dict[str, str],
        operation_group: str = "Other",
        order: int | None = None
    ) -> Callable[[MacroFn], Macro]:
        '''Registers a operation macro.
        
        The decorated function should take one argument, a `PositionedTile`.

        The macro is invoked when the operation matches `pattern`. 

        `operation_hints` is a list of (operation, user-friendly representation) pairs.
        Each operation should be valid for the macro. The representation should typically 
        be related to the operation provided, as it will be passed to the user. 
        
        `operation_group` is a key used to group operation macros together. It should
        be a user-friendly string.

        The lower `order` is, the earlier the macro is prioritized (loosely).
        If `order` is `None` or not given, the macro is given the least priority (loosely).
        '''
        def deco(fn: MacroFn) -> Macro:
            macro = Macro(pattern, fn, operation_hints, operation_group)
            if order is None:
                self.macros.append(macro)
            else:
                self.macros.insert(order, macro)
            return macro
        return deco

    def expand_into(
        self,
        tiles: list[PositionedTile],
        tile: PositionedTile,
        operation: str,
    ) -> tuple[int, int, int, int]:
        '''Expand the operation, returns the resulting tiles'''
        tiles = []
        deltas = tile.position
        for macro in reversed(self.macros):
            match = macro.match(operation)
            if match is not None:
                deltas = macro.expand_into(tiles, tile, match)
                break
        else:
            raise fgdahsjkfgasjkdgfhjdsagfhjsakgfhjsakd
        return deltas

class Macro:
    '''Handles a single operation'''
    def __init__(
        self,
        pattern: str,
        fn: MacroFn,
        hints: dict[str, str],
        group: str
    ):
        self.pattern = pattern
        self.fn = fn
        self.hints = hints
        self.group = group

    def match(self, operation: str) -> tuple[str, ...] | None:
        '''Can this macro take the operation?
        
        Returns the matched groups if possible, else returns `None`.
        '''
        matches = re.fullmatch(self.pattern, operation)
        if matches is not None:
            return matches.groups()
    
    def expand_into(self, tiles: list[PositionedTile], tile: PositionedTile, groups: tuple[str, ...]) -> tuple[int, int, int, int]:
        '''Handle the operation'''
        return self.fn(tiles, tile, groups)


def setup(bot: Bot):
    '''Get the operation macro instance'''
    macros = OperationMacros(bot)
    bot.operation_macros = macros
    
    @macros.macro(
        pattern=r"anim(\d+)?",
        operation_hints={"anim": "`anim<number>` (Animate the tile in place for <number> animation cycles)"},
        operation_group="Movement & Animation"
    )
    def animate(tiles: list[PositionedTile], tile: PositionedTile, groups: tuple[str, ...]) -> tuple[int, int, int, int]:
        if groups[0] is None:
            count = 1
        else:
            count = int(groups[0])
        x, y, z, t = tile.position
        out = []
        for dt in range(count):
            for i in range(4):
                new = tile.reposition((x, y, z, t + dt * 4 + i))
                new.variants.append(f"a{i}s")
                out.append(new)
        tiles.extend(out[1:])
        return (0, 0, 0, count)
    
    @macros.macro(
        pattern=r"m([udlr]+)",
        operation_hints={"mr": "`m<udlr>`: Move the tile across space in a single frame, e.g. `mrrd`."},
        operation_group="Movement & Animation"
    )
    def move_once(tiles: list[PositionedTile], tile: PositionedTile, groups: tuple[str, ...]) -> tuple[int, int, int, int]:
        dx = groups[0].count("r") - groups[0].count("l")
        dy = groups[0].count("d") - groups[0].count("u")
        x, y, z, t = tile.position
        new = tile.reposition((x + dx, y + dy, z, t + 1))
        if abs(dx) >= abs(dy):
            if dx >= 0:
                new.variants.append("rs")
            else:
                new.variants.append("ls")
        else:
            if dy >= 0:
                new.variants.append("ds")
            else:
                new.variants.append("us")
        tiles.append(new)
        tiles.append(PositionedTile.blank((x , y, z, t + 1)))
        return (dx, dy, 0, 1)
    
    @macros.macro(
        pattern=r"([udlr]+)",
        operation_hints={"r": "`<udlr>`: Move the object like YOU!"},
        operation_group="Movement & Animation"
    )
    def move_you(tiles: list[PositionedTile], tile: PositionedTile, groups: tuple[str, ...]) -> tuple[int, int, int, int]:
        dx = dy = 0
        x, y, z, t = tile.position
        animation = 0
        for dt, dir in enumerate(groups[0]):
            tiles.append(PositionedTile.blank((x + dx, y + dy, z, t + dt + 1)))
            if dir == "r":
                dx += 1
                dir_variant = "rs"
            elif dir == "u":
                dy -= 1
                dir_variant = "us"
            elif dir == "l":
                dx -= 1
                dir_variant = "ls"
            else:
                dy += 1
                dir_variant = "ds"
            new = tile.reposition((x + dx, y + dy, z, t + dt + 1))
            new.variants.append(dir_variant)
            anim_frame = (animation + dt + 1) % 4
            new.variants.append(f"a{anim_frame}s")
            tiles.append(new)
        
        return (dx, dy, 0, 1)

    return macros
