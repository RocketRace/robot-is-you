from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .. import errors
from ..tile import Grid, RawTile

if TYPE_CHECKING:
    from ...ROBOT import Bot
    MacroFn = Callable[['MacroCtx'], tuple[int, int, int]]

@dataclass
class MacroCtx:
    grid: Grid[RawTile]
    tile: list[RawTile] # exactly one
    position: tuple[int, int, int]
    groups: tuple[str, ...]
    operation: str

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

    def get_all(self) -> dict[str, list[str]]:
        '''All the operations!'''
        out = {}
        for macro in self.macros:
            out.setdefault(macro.group, []).extend(list(macro.hints.values()))
        return out

    def expand_into(
        self,
        grid: Grid[RawTile],
        tile: list[RawTile], # exactly one
        position: tuple[int, int, int],
        operation: str,
    ) -> tuple[int, int, int]:
        '''Expand the operation into the given tile dict'''
        deltas = 0, 0, 0
        for macro in reversed(self.macros):
            groups = macro.match(operation)
            if groups is not None:
                deltas = macro.expand_into(grid, tile, position, groups, operation)
                break
        else:
            raise errors.OperationNotFound(operation, position, tile[-1])
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
    
    def expand_into(self, grid: Grid[RawTile], tile: list[RawTile], position: tuple[int, int, int], groups: tuple[str, ...], operation: str) -> tuple[int, int, int]:
        '''Handle the operation'''
        return self.fn(MacroCtx(grid, tile, position, groups, operation))


async def setup(bot: Bot):
    '''Get the operation macro instance'''
    macros = OperationMacros(bot)
    bot.operation_macros = macros
    
    @macros.macro(
        pattern=r"idle(\d+)?",
        operation_hints={"idle": "`idle<number>` Animate the tile in place for <number> animation cycles"},
        operation_group="Movement & Animation"
    )
    def idle(ctx: MacroCtx) -> tuple[int, int, int]:
        if ctx.groups[0] is None:
            count = 1
        else:
            count = int(ctx.groups[0])
        x, y, t = ctx.position
        ctx.tile[-1].variants.append("") # Temporary
        for dt in range(count):
            for i in range(4):
                ctx.tile[-1].variants[-1] = f"a{i}s"
                ctx.grid.setdefault((x, y, t + 4 * dt + i), []).append(ctx.tile[-1].copy())
        return (0, 0, count)
    
    @macros.macro(
        pattern=r"m([udlr]+)",
        operation_hints={"mr": "`m<udlr>`: Move the tile across space in a single frame, e.g. `mrrd`."},
        operation_group="Movement & Animation"
    )
    def move_once(ctx: MacroCtx) -> tuple[int, int, int]:
        groups = ctx.groups
        dx = groups[0].count("r") - groups[0].count("l")
        dy = groups[0].count("d") - groups[0].count("u")
        
        original = ctx.tile[-1].copy()
        # note the order of lines
        original.ephemeral = True
        ctx.grid.setdefault(ctx.position, []).append(original)
        
        if abs(dx) >= abs(dy):
            if dx >= 0:
                ctx.tile[-1].variants.append("rs")
            else:
                ctx.tile[-1].variants.append("ls")
        else:
            if dy >= 0:
                ctx.tile[-1].variants.append("ds")
            else:
                ctx.tile[-1].variants.append("us")
        
        x, y, t = ctx.position
        if x + dx < 0 or y + dy < 0:
            raise errors.MovementOutOfFrame(ctx.operation, ctx.position, ctx.tile[-1])
        ctx.grid.setdefault((x + dx, y + dy, t + 1), []).append(ctx.tile[-1].copy())
        return (dx, dy, 1)
    
    @macros.macro(
        pattern=r"([udlri]+)",
        operation_hints={"r": "`<udlri>`: Move the object like YOU!"},
        operation_group="Movement & Animation"
    )
    def move_you(ctx: MacroCtx) -> tuple[int, int, int]:
        original = ctx.tile[-1].copy()
        original.ephemeral = True
        ctx.grid.setdefault(ctx.position, []).append(original)
        ctx.tile[-1].variants.append("") # temporary
        ctx.tile[-1].variants.append("") # temporary
        
        dx = dy = 0
        x, y, t = ctx.position
        animation = 0
        movements = ctx.groups[0]
        ddt = 0
        for dt, dir in enumerate(movements):
            if dir == "r":
                dx += 1
                dir_variant = "rs"
            elif dir == "u":
                dy -= 1
                dir_variant = "us"
            elif dir == "l":
                dx -= 1
                dir_variant = "ls"
            elif dir == "d":
                dy += 1
                dir_variant = "ds"
            else:
                ddt += 1
                dir_variant = "nothing"
            ctx.tile[-1].variants[-2] = dir_variant
            anim_frame = (animation + dt - ddt + 1) % 4
            ctx.tile[-1].variants[-1] = f"a{anim_frame}s"
            new = ctx.tile[-1].copy()
            new.ephemeral = True
            if x + dx < 0 or y + dy < 0:
                raise errors.MovementOutOfFrame(ctx.operation, ctx.position, ctx.tile[-1])
            # the +1 is required as dt starts from 0
            ctx.grid.setdefault((x + dx, y + dy, t + dt + 1), []).append(new)
        return (dx, dy, len(movements))

    return macros
