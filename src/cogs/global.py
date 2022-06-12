from __future__ import annotations

import os
import re
from datetime import datetime
from io import BytesIO
from json import load
from os import listdir
from time import time
from typing import TYPE_CHECKING, Any

from PIL.ImageChops import constant

import aiohttp
import discord
import lark
from discord.ext import commands
from lark import Lark
from lark.lexer import Token
from lark.tree import Tree

from .. import constants, errors
from ..db import CustomLevelData, LevelData
from ..tile import RawTile
from ..types import Context

if TYPE_CHECKING:
    from ...ROBOT import Bot

class GlobalCog(commands.Cog, name="Baba Is You"):
    def __init__(self, bot: Bot):
        self.bot = bot
        with open("config/leveltileoverride.json") as f:
            j = load(f)
            self.level_tile_override = j
        with open("src/tile_grammar.lark") as f:
            self.lark = Lark(f.read(), start="row", parser="lalr")

    # Check if the bot is loading
    async def cog_check(self, ctx):
        '''Only if the bot is not loading assets'''
        return not self.bot.loading

    async def handle_variant_errors(self, ctx: Context, err: errors.VariantError):
        '''Handle errors raised in a command context by variant handlers'''
        word, variant, *rest = err.args
        msg = f"The variant `{variant}` for `{word}` is invalid"
        if isinstance(err, errors.BadTilingVariant):
            tiling = rest[0]
            return await ctx.error(
                f"{msg}, since it can't be applied to tiles with tiling type `{tiling}`."
            )
        elif isinstance(err, errors.TileNotText):
            return await ctx.error(
                f"{msg}, since the tile is not text."
            )
        elif isinstance(err, errors.BadPaletteIndex):
            return await ctx.error(
                f"{msg}, since the color is outside the palette."
            )
        elif isinstance(err, errors.BadLetterVariant):
            return await ctx.error(
                f"{msg}, since letter-style text can only be 1 or 2 letters wide."
            )
        elif isinstance(err, errors.BadMetaVariant):
            depth = rest[0]
            return await ctx.error(
                f"{msg}. `{depth}` is greater than the maximum meta depth, which is `{constants.MAX_META_DEPTH}`."
            )
        elif isinstance(err, errors.TileDoesntExist):
            return await ctx.error(
                f"{msg}, since the tile doesn't exist in the database."
            )
        elif isinstance(err, errors.UnknownVariant):
            return await ctx.error(
                f"The variant `{variant}` is not valid."
            )
        else:
            return await ctx.error(f"{msg}.")

    async def handle_custom_text_errors(self, ctx: Context, err: errors.TextGenerationError):
        '''Handle errors raised in a command context by variant handlers'''
        text, *rest = err.args
        msg = f"The text {text} couldn't be generated automatically"
        if isinstance(err, errors.BadLetterStyle):
            return await ctx.error(
                f"{msg}, since letter style can only applied to a single row of text."
            )
        elif isinstance(err, errors.TooManyLines):
            return await ctx.error(
                f"{msg}, since it has too many lines."
            )
        elif isinstance(err, errors.LeadingTrailingLineBreaks):
            return await ctx.error(
                f"{msg}, since there's `/` characters at the start or end of the text."
            )
        elif isinstance(err, errors.BadCharacter):
            mode, char = rest
            return await ctx.error(
                f"{msg}, since the letter {char} doesn't exist in '{mode}' mode."
            )
        elif isinstance(err, errors.CustomTextTooLong):
            return await ctx.error(
                f"{msg}, since it's too long ({len(text)})."
            )
        else:
            return await ctx.error(f"{msg}.")
    
    async def handle_operation_errors(self, ctx: Context, err: errors.OperationError):
        '''Handle errors raised in a command context by operation macros'''
        operation, pos, tile, *rest = err.args
        msg = f"The operation {operation} is not valid"
        if isinstance(err, errors.OperationNotFound):
            return await ctx.error(
                f"The operation `{operation}` for `{tile.name}` could not be found."
            )
        elif isinstance(err, errors.MovementOutOfFrame):
            return await ctx.error(
                f"Tried to move out of bounds with the `{operation}` operation for `{tile.name}`."
            )
        else:
            return await ctx.error(f"The operation `{operation}` failed for `{tile.name}`.")

    def parse_row(self):
        pass

    async def render_tiles(self, ctx: Context, *, objects: str, is_rule: bool):
        '''Performs the bulk work for both `tile` and `rule` commands.'''
        await ctx.typing()
        start = time()
        tiles = objects.lower().strip()
        
        # replace emoji with their :text: representation
        builtin_emoji = {
            ord("\u24dc"): ":m:", # lower case circled m
            ord("\u24c2"): ":m:", # upper case circled m
            ord("\U0001f199"): ":up:", # up! emoji
            ord("\U0001f637"): ":mask:", # mask emoji
            ord("\ufe0f"): None
        }
        tiles = tiles.translate(builtin_emoji)
        tiles = re.sub(r'<a?(:[a-zA-Z0-9_]{2,32}:)\d{1,21}>', r'\1', tiles)
        
        # ignore all these
        tiles = tiles.replace("```\n", "").replace("\\", "").replace("`", "")

        # Determines if this should be a spoiler
        spoiler = tiles.count("||") >= 2
        tiles = tiles.replace("|", "")
        
        # Check for empty input
        if not tiles:
            return await ctx.error("Input cannot be blank.")

        # Handle flags *first*, before even splitting
        flag_patterns = (
            r"(?:^|\s)(?:--background|-b)(?:=(\d)/(\d))?(?:$|\s)",
            r"(?:^|\s)(?:--palette=|-p=|palette:)(\w+)(?:$|\s)",
            r"(?:^|\s)(?:--raw|-r)(?:=([a-zA-Z_0-9]+))?(?:$|\s)",
            r"(?:^|\s)(?:--letter|-l)(?:$|\s)",
            r"(?:^|\s)(?:(--delay=|-d=)(\d+))(?:$|\s)",
            r"(?:^|\s)(?:(--frames=|-f=)(\d))(?:$|\s)",
        )
        background = None
        for match in re.finditer(flag_patterns[0], tiles):
            if match.group(1) is not None:
                tx, ty = int(match.group(1)), int(match.group(2))
                if not (0 <= tx <= 7 and 0 <= ty <= 5):
                    return await ctx.error("The provided background color is invalid.")
                background = tx, ty
            else:
                background = (0, 4)
        palette = "default"
        for match in re.finditer(flag_patterns[1], tiles):
            palette = match.group(1)
            if palette + ".png" not in listdir("data/palettes"):
                return await ctx.error(f"Could not find a palette with name \"{palette}\".")
        raw_output = False
        raw_name = ""
        for match in re.finditer(flag_patterns[2], tiles):
            raw_output = True
            if match.group(1) is not None:
                raw_name = match.group(1)
        default_to_letters = False
        for match in re.finditer(flag_patterns[3], tiles):
            default_to_letters = True
        delay = 200
        for match in re.finditer(flag_patterns[4], tiles):
            delay = int(match.group(2))
            if delay < 1 or delay > 1000:
                return await ctx.error(f"Delay must be between 1 and 1000 milliseconds.")
        frame_count = 3
        for match in re.finditer(flag_patterns[5], tiles):
            frame_count = int(match.group(2))
            if frame_count < 1 or frame_count > 3:
                return await ctx.error(f"The frame count must be 1, 2 or 3.")
        
        # Clean up
        for pattern in flag_patterns:
            tiles = re.sub(pattern, " ", tiles)

        # read from file if nothing (beyond flags) is provided
        if not tiles.strip():
            attachments = ctx.message.attachments
            if len(attachments) > 0:
                file = attachments[0]
                if file.size > constants.MAX_INPUT_FILE_SIZE:
                    await ctx.error(f"The file is too large ({file.size} bytes). Maximum: {constants.MAX_INPUT_FILE_SIZE} bytes")
                try:
                    tiles = (await file.read()).decode("utf-8").lower().strip()
                    if file.filename != "message.txt":
                        raw_name = file.filename.split(".")[0]
                except UnicodeDecodeError:
                    await ctx.error("The file contains invalid UTF-8. Make sure it's not corrupt.")

        
        # Split input into lines
        rows = tiles.splitlines()
        
        expanded_tiles: dict[tuple[int, int, int], list[RawTile]] = {}
        previous_tile: list[RawTile] = []
        # Do the bulk of the parsing here:
        for y, row in enumerate(rows):
            x = 0
            try:
                row_maybe = row.strip()
                if not row_maybe:
                    continue
                tree = self.lark.parse(row_maybe)
            except lark.UnexpectedCharacters as e:
                return await ctx.error(f"Invalid character `{e.char}` in row {y}, around `... {row[e.column - 5: e.column + 5]} ...`")
            except lark.UnexpectedToken as e:
                mistake_kind = e.match_examples(
                    self.lark.parse, 
                    {
                        "unclosed": [
                            "(baba",
                            "[this ",
                            "\"rule",
                        ],
                        "missing": [
                            ":red",
                            "baba :red",
                            "&baba",
                            "baba& keke",
                            ">baba",
                            "baba> keke"
                        ],
                        "variant": [
                            "baba: keke",
                        ]
                    }
                )
                around = f"`... {row[e.column - 5 : e.column + 5]} ...`"
                if mistake_kind == "unclosed":
                    return await ctx.error(f"Unclosed brackets or quotes! Expected them to close around {around}.")
                elif mistake_kind == "missing":
                    return await ctx.error(f"Missing a tile in row {y}! Make sure not to have spaces between `&`, `:`, or `>`!\nError occurred around {around}.")
                elif mistake_kind == "variant":
                    return await ctx.error(f"Empty variant in row {y}, around {around}.")
                else:
                    return await ctx.error(f"Invalid syntax in row {y}, around {around}.")
            except lark.UnexpectedEOF as e:
                return await ctx.error(f"Unexpected end of input in row {y}.")
            for line in tree.children: 
                line: Tree
                line_text_mode: bool | None = None
                line_variants: list[str] = []

                if line.data == "text_chain":
                    line_text_mode = True
                elif line.data == "tile_chain":
                    line_text_mode = False
                elif line.data == "text_block":
                    line_text_mode = True
                elif line.data == "tile_block":
                    line_text_mode = False
                
                if line.data in ("text_block", "tile_block", "any_block"):
                    *stacks, variants = line.children 
                    variants: Tree
                    for variant in variants.children: 
                        variant: Token
                        line_variants.append(variant.value)
                else:
                    stacks = line.children
                
                for stack in stacks: 
                    stack: Tree

                    blobs: list[tuple[bool | None, list[str], Tree]] = []

                    if stack.data == "blob_stack":
                        for variant_blob in stack.children:
                            blob, variants = variant_blob.children 
                            blob: Tree
                            variants: Tree
                            
                            blob_text_mode: bool | None = None
                            
                            stack_variants = []
                            for variant in variants.children:
                                variant: Token
                                stack_variants.append(variant.value)
                            if blob.data == "text_blob":
                                blob_text_mode = True
                            elif blob.data == "tile_blob":
                                blob_text_mode = False
                            
                            blobs.append((blob_text_mode, stack_variants, blob))
                    else:
                        blobs = [(None, [], stack)] 

                    for blob_text_mode, stack_variants, blob in blobs:
                        for process in blob.children: 
                            process: Tree
                            t = 0

                            unit, *changes = process.children 
                            unit: Tree
                            changes: list[Tree]
                            
                            object, variants = unit.children 
                            object: Token
                            obj = object.value
                            variants: Tree
                            
                            final_variants: list[str] = [
                                var.value 
                                for var in variants.children
                            ]

                            def append_extra_variants(final_variants: list[str]):
                                '''IN PLACE'''
                                final_variants.extend(stack_variants)
                                final_variants.extend(line_variants)

                            def handle_text_mode(obj: str) -> str:
                                '''RETURNS COPY'''
                                text_delta = -1 if blob_text_mode is False else blob_text_mode or 0
                                text_delta += -1 if line_text_mode is False else line_text_mode or 0
                                text_delta += is_rule
                                if text_delta == 0:
                                    return obj
                                elif text_delta > 0:
                                    for _ in range(text_delta):
                                        if obj.startswith("tile_"):
                                            obj = obj[5:]
                                        else:
                                            obj = f"text_{obj}"
                                    return obj
                                else:
                                    for _ in range(text_delta):
                                        if obj.startswith("text_"):
                                            obj = obj[5:]
                                        else:
                                            raise RuntimeError("this should never happen")
                                            # TODO: handle this explicitly
                                    return obj

                            obj = handle_text_mode(obj)
                            append_extra_variants(final_variants)

                            dx = dy = 0
                            temp_tile: list[RawTile] = [RawTile(obj, final_variants, ephemeral=False)]
                            last_hack = False
                            for change in changes:
                                if change.data == "transform":
                                    last_hack = False
                                    seq, unit = change.children 
                                    seq: str

                                    count = len(seq)
                                    still = temp_tile.pop()
                                    still.ephemeral = True
                                    if still.is_previous:
                                        still = previous_tile[-1]
                                    else:
                                        previous_tile[-1:] = [still]
                                    
                                    for dt in range(count):
                                        expanded_tiles.setdefault((x + dx, y + dy, t + dt), []).append(still)
                                        
                                    object, variants = unit.children 
                                    object: Token
                                    obj = object.value
                                    obj = handle_text_mode(obj)
                                    
                                    final_variants = [var.value for var in variants.children]
                                    append_extra_variants(final_variants)
                                    
                                    temp_tile.append(
                                        RawTile(
                                            obj,
                                            final_variants,
                                            ephemeral=False
                                        )
                                    )
                                    t += count

                                elif change.data == "operation":
                                    last_hack = True
                                    oper = change.children[0] 
                                    oper: Token
                                    try:
                                        ddx, ddy, dt = self.bot.operation_macros.expand_into(
                                            expanded_tiles,
                                            temp_tile,
                                            (x + dx, y + dy, t),
                                            oper.value
                                        )
                                    except errors.OperationError as err:
                                        return await self.handle_operation_errors(ctx, err)
                                    dx += ddx
                                    dy += ddy
                                    t += dt
                            # somewhat monadic behavior
                            if not last_hack:
                                expanded_tiles.setdefault((x + dx, y + dy, t), []).extend(temp_tile[:])
                    x += 1

        # Get the dimensions of the grid
        width = max(expanded_tiles, key=lambda pos: pos[0])[0] + 1
        height = max(expanded_tiles, key=lambda pos: pos[1])[1] + 1
        duration = 1 + max(t for _, _, t in expanded_tiles)

        temporal_maxima: dict[tuple[int, int], tuple[int, list[RawTile]]] = {}
        for (x, y, t), tile_stack in expanded_tiles.items():
            if (x, y) in temporal_maxima and temporal_maxima[x, y][0] < t:
                persistent = [tile for tile in tile_stack if not tile.ephemeral]
                if len(persistent) != 0:
                    temporal_maxima[x, y] = t, persistent
            elif (x, y) not in temporal_maxima:
                persistent = [tile for tile in tile_stack if not tile.ephemeral]
                if len(persistent) != 0:
                    temporal_maxima[x, y] = t, persistent
        # Pad the grid across time
        for (x, y), (t_star, tile_stack) in temporal_maxima.items():
            for t in range(t_star, duration - 1):
                if (x, y, t + 1) not in expanded_tiles:
                    expanded_tiles[x, y, t + 1] = tile_stack
                else:
                    expanded_tiles[x, y, t + 1] = tile_stack + expanded_tiles[x, y, t + 1]
                    
        # filter out blanks before rendering
        expanded_tiles = {index: [tile for tile in stack if not tile.is_empty] for index, stack in expanded_tiles.items()}
        expanded_tiles = {index: stack for index, stack in expanded_tiles.items() if len(stack) != 0}

        # Don't proceed if the request is too large.
        # (It shouldn't be that long to begin with because of Discord's 2000 character limit)
        if width * height * duration > constants.MAX_VOLUME:
            return await ctx.error(f"Too large of an animation ({width * height * duration}). An animation may have up to {constants.MAX_VOLUME} tiles, including tiles repeated in frames.")
        if width > constants.MAX_WIDTH:
            return await ctx.error(f"Too wide ({width}). You may only render scenes up to {constants.MAX_WIDTH} tiles wide.")
        if height > constants.MAX_HEIGHT:
            return await ctx.error(f"Too high ({height}). You may only render scenes up to {constants.MAX_HEIGHT} tiles tall.")
        if duration > constants.MAX_DURATION:
            return await ctx.error(f"Too many frames ({duration}). You may only render scenes with up to {constants.MAX_DURATION} animation frames.")
        
        try:
            # Handles variants based on `:` affixes
            buffer = BytesIO()
            extra_buffer = BytesIO() if raw_output else None
            extra_names = [] if raw_output else None
            full_objects = await self.bot.variant_handlers.handle_grid(
                expanded_tiles,
                (width, height),
                raw_output=raw_output,
                extra_names=extra_names,
                default_to_letters=default_to_letters
            )
            if extra_names is not None and not raw_name:
                if len(extra_names) == 1:
                    raw_name = extra_names[0]
                else:
                    raw_name = constants.DEFAULT_RENDER_ZIP_NAME
            full_tiles = await self.bot.renderer.render_full_tiles(
                full_objects,
                palette=palette,
                random_animations=True
            )
            await self.bot.renderer.render(
                full_tiles,
                grid_size=(width, height),
                duration=duration,
                palette=palette,
                background=background, 
                out=buffer,
                delay=delay,
                frame_count=frame_count,
                upscale=not raw_output,
                extra_out=extra_buffer,
                extra_name=raw_name,
            )
        except errors.TileNotFound as e:
            word = e.args[0]
            name = word.name
            if word.name.startswith("tile_") and await self.bot.db.tile(name[5:]) is not None:
                return await ctx.error(f"The tile `{name}` could not be found. Perhaps you meant `{name[5:]}`?")
            if await self.bot.db.tile("text_" + name) is not None:
                return await ctx.error(f"The tile `{name}` could not be found. Perhaps you meant `{'text_' + name}`?")
            return await ctx.error(f"The tile `{name}` could not be found.")
        except errors.BadTileProperty as e:
            word, (w, h) = e.args
            return await ctx.error(f"The tile `{word.name}` could not be made into a property, because it's too big (`{w} by {h}`).")
        except errors.EmptyTile as e:
            return await ctx.error("Cannot use blank tiles in that context.")
        except errors.EmptyVariant as e:
            word = e.args[0]
            return await ctx.error(
                f"You provided an empty variant for `{word.name}`."
            )
        except errors.VariantError as e:
            return await self.handle_variant_errors(ctx, e)
        except errors.TextGenerationError as e:
            return await self.handle_custom_text_errors(ctx, e)
        
        filename = datetime.utcnow().strftime(r"render_%Y-%m-%d_%H.%M.%S.gif")
        delta = time() - start
        msg = f"*Rendered in {delta:.2f} s*"
        if extra_buffer is not None and raw_name:
            extra_buffer.seek(0)
            await ctx.reply(content=f'{msg}\n*Raw files:*', files=[discord.File(extra_buffer, filename=f"{raw_name}.zip"),discord.File(buffer, filename=filename, spoiler=spoiler)])
        else:
            await ctx.reply(content=msg, file=discord.File(buffer, filename=filename, spoiler=spoiler))
        

    @commands.command(aliases=["text"])
    @commands.cooldown(5, 8, type=commands.BucketType.channel)
    async def rule(self, ctx: Context, *, objects: str = ""):
        '''Renders the text tiles provided. 
        
        If not found, the bot tries to auto-generate them! (See the `make` command for more.)

        **Flags**
        * `--palette=<...>` (`-P=<...>`): Recolors the output gif. See `search type:palettes` command for palettes.
        * `--background=[...]` (`-B=[...]`): Enables background color. If no argument is given, defaults to black. The argument must be a palette index ("x/y").
        * `--raw` (`-R`): Enables raw mode. The sprites are sent in a ZIP file as well as normally. By default, sprites have no color.
        * `--letter` (`-L`): Enables letter mode. Custom text that has 2 letters in it will be rendered in "letter" mode.
        * `--delay=<...>` (`-D=<...>`): Alter the delay (in milliseconds) between frames.
        * `--frames=<...>` (`-F=<...>`): How many wobble frames will be shown? (1, 2 or 3)
        
        **Variants, Operations & Transformations**
        * `:variant`: Append `:variant` to a tile to change color or sprite of a tile. See the `variants` command for more.
        * `!operation`: Apply a macro operation to a tile. See the `operations` command for more.
        * `>`: Transform the tile on the left to the tile on the right! Examples: `baba>keke`, `rock>>>flag>dust>>-`

        **Useful tips:**
        * `-` : Shortcut for an empty tile. 
        * `&` : Stacks tiles on top of each other.
        * `tile_` : `tile_object` renders regular objects.
        * `,` : `tile_x,y,...` is expanded into `tile_x tile_y ...`
        * `||` : Marks the output gif as a spoiler. 
        * `(baba keke)` groups tiles together, for easier variants
        * `"baba is you"` makes all the tiles inside text
        * `[baba keke me]` makes all the tiles inside objects
        
        **Example commands:**
        `rule baba is you`
        `rule -B rock is ||push||`
        `rule -P=test tile_baba on baba is word`
        `rule baba eat baba - tile_baba tile_baba:l`
        '''
        await self.render_tiles(ctx, objects=objects, is_rule=True)

    # Generates an animated gif of the tiles provided, using the default palette
    @commands.command()
    @commands.cooldown(5, 8, type=commands.BucketType.channel)
    async def tile(self, ctx: Context, *, objects: str = ""):
        '''Renders the tiles provided.

       **Flags**
        * `--palette=<...>` (`-P=<...>`): Recolors the output gif. See `search type:palettes` command for palettes.
        * `--background=[...]` (`-B=[...]`): Enables background color. If no argument is given, defaults to black. The argument must be a palette index ("x/y").
        * `--raw` (`-R`): Enables raw mode. The sprites are sent in a ZIP file as well as normally. By default, sprites have no color.
        * `--letter` (`-L`): Enables letter mode. Custom text that has 2 letters in it will be rendered in "letter" mode.
        * `--delay=<...>` (`-D=<...>`): Alter the delay (in milliseconds) between frames.
        * `--frames=<...>` (`-F=<...>`): How many wobble frames will be shown? (1, 2 or 3)

        **Variants**
        * `:variant`: Append `:variant` to a tile to change color or sprite of a tile. See the `variants` command for more.
        * `!operation`: Apply a macro operation to a tile. See the `operations` command for more.
        * `>`: Transform the tile on the left to the tile on the right! Examples: `baba>keke`, `rock>>>flag>dust>>-`

        **Useful tips:**
        * `-` : Shortcut for an empty tile. 
        * `&` : Stacks tiles on top of each other.
        * `text_` : `text_object` renders text objects.
        * `,` : `text_x,y,...` is expanded into `text_x text_y...`
        * `||` : Marks the output gif as a spoiler. 
        
        **Example commands:**
        `tile baba - keke`
        `tile --palette=marshmallow keke:d baba:s`
        `tile text_baba,is,you`
        `tile baba&flag ||cake||`
        `tile -P=mountain -B baba bird:l`
        '''
        await self.render_tiles(ctx, objects=objects, is_rule=False)

    async def search_levels(self, query: str, **flags: Any) -> list[tuple[tuple[str, str], LevelData]]:
        '''Finds levels by query.
        
        Flags:
        * `map`: Which map screen the level is from.
        * `world`: Which levelpack / world the level is from.
        '''
        levels: list[tuple[tuple[str, str], LevelData]] = []
        found: set[tuple[str, str]] = set()
        f_map = flags.get("map")
        f_world = flags.get("world")
        async with self.bot.db.conn.cursor() as cur:
            # [world]/[levelid]
            parts = query.split("/", 1)
            if len(parts) == 2:
                await cur.execute(
                    '''
                    SELECT * FROM levels 
                    WHERE 
                        world == :world AND
                        id == :id AND (
                            :f_map IS NULL OR LOWER(parent) == LOWER(:f_map)
                        ) AND (
                            :f_world IS NULL OR LOWER(world) == LOWER(:f_world)
                        );
                    ''',
                    dict(world=parts[0], id=parts[1], f_map=f_map, f_world=f_world)
                )
                row = await cur.fetchone()
                if row is not None:
                    data = LevelData.from_row(row)
                    if (data.world, data.id) not in found:
                        found.add((data.world, data.id))
                        levels.append(((data.world, data.id), data))


            # This system ensures that baba worlds are 
            # *always* prioritized over modded worlds,
            # even if the modded query belongs to a higher tier.
            # 
            # A real example of the naive approach failing is 
            # with the query "map", matching `baba/106level` by name
            # and `alphababa/map` by level ID. Even though name 
            # matches are lower priority than ID matches, we want
            # ths to return `baba/106level` first.
            maybe_parts = query.split(" ", 1)
            if len(maybe_parts) == 2:
                possible_queries = [
                    ("baba", query),
                    (maybe_parts[0], maybe_parts[1]),
                    (f_world, query)
                ]
            else:
                possible_queries = [
                    ("baba", query),
                    (f_world, query)
                ]
            if f_world is not None:
                possible_queries = possible_queries[1:]

            for f_world, query in possible_queries:
                # someworld/[levelid]
                await cur.execute(
                    '''
                    SELECT * FROM levels
                    WHERE id == :id AND (
                        :f_map IS NULL OR LOWER(parent) == LOWER(:f_map)
                    ) AND (
                        :f_world IS NULL OR LOWER(world) == LOWER(:f_world)
                    )
                    ORDER BY CASE world 
                        WHEN :default
                        THEN NULL 
                        WHEN :museum
                        THEN ""
                        WHEN :new_adv
                        THEN ""
                        ELSE world 
                    END ASC;
                    ''',
                    dict(
                        id=query, 
                        f_map=f_map, 
                        f_world=f_world, 
                        default=constants.BABA_WORLD, 
                        museum=constants.MUSEUM_WORLD, 
                        new_adv=constants.NEW_ADVENTURES_WORLD
                    )
                )
                for row in await cur.fetchall():
                    data = LevelData.from_row(row)
                    if (data.world, data.id) not in found:
                        found.add((data.world, data.id))
                        levels.append(((data.world, data.id), data))
                
                # [parent]-[map_id]
                segments = query.split("-")
                if len(segments) == 2:
                    await cur.execute(
                        '''
                        SELECT * FROM levels 
                        WHERE LOWER(parent) == LOWER(:parent) AND (
                            UNLIKELY(map_id == :map_id) OR (
                                style == 0 AND 
                                CAST(number AS TEXT) == :map_id
                            ) OR (
                                style == 1 AND
                                LENGTH(:map_id) == 1 AND
                                number == UNICODE(:map_id) - UNICODE("a")
                            ) OR (
                                style == 2 AND 
                                SUBSTR(:map_id, 1, 5) == "extra" AND
                                number == CAST(TRIM(SUBSTR(:map_id, 6)) AS INTEGER) - 1
                            )
                        ) AND (
                            :f_map IS NULL OR LOWER(parent) == LOWER(:f_map)
                        ) AND (
                            :f_world IS NULL OR LOWER(world) == LOWER(:f_world)
                        ) ORDER BY CASE world 
                            WHEN :default
                            THEN NULL 
                            WHEN :museum
                            THEN ""
                            WHEN :new_adv
                            THEN ""
                            ELSE world 
                        END ASC;
                        ''',
                        dict(
                            parent=segments[0], 
                            map_id=segments[1], 
                            f_map=f_map, 
                            f_world=f_world, 
                            default=constants.BABA_WORLD,
                            museum=constants.MUSEUM_WORLD, 
                            new_adv=constants.NEW_ADVENTURES_WORLD
                        )
                    )
                    for row in await cur.fetchall():
                        data = LevelData.from_row(row)
                        if (data.world, data.id) not in found:
                            found.add((data.world, data.id))
                            levels.append(((data.world, data.id), data))

                # [name]
                await cur.execute(
                    '''
                    SELECT * FROM levels
                    WHERE name == :name AND (
                        :f_map IS NULL OR LOWER(parent) == LOWER(:f_map)
                    ) AND (
                        :f_world IS NULL OR LOWER(world) == LOWER(:f_world)
                    )
                    ORDER BY CASE world 
                        WHEN :default
                        THEN NULL 
                        WHEN :museum
                        THEN ""
                        WHEN :new_adv
                        THEN ""
                        ELSE world 
                    END ASC;
                    ''',
                    dict(
                        name=query, 
                        f_map=f_map, 
                        f_world=f_world, 
                        default=constants.BABA_WORLD, 
                        museum=constants.MUSEUM_WORLD, 
                        new_adv=constants.NEW_ADVENTURES_WORLD
                    )
                )
                for row in await cur.fetchall():
                    data = LevelData.from_row(row)
                    if (data.world, data.id) not in found:
                        found.add((data.world, data.id))
                        levels.append(((data.world, data.id), data))

                # [name-ish]
                await cur.execute(
                    '''
                    SELECT * FROM levels
                    WHERE INSTR(name, :name) AND (
                        :f_map IS NULL OR LOWER(parent) == LOWER(:f_map)
                    ) AND (
                        :f_world IS NULL OR LOWER(world) == LOWER(:f_world)
                    )
                    ORDER BY COALESCE(
                        CASE world 
                            WHEN :default
                            THEN NULL 
                            WHEN :museum
                            THEN ""
                            WHEN :new_adv
                            THEN ""
                            ELSE world 
                        END,
                        INSTR(name, :name)
                    ) ASC, number DESC;
                    ''',
                    dict(
                        name=query, 
                        f_map=f_map, 
                        f_world=f_world, 
                        default=constants.BABA_WORLD, 
                        museum=constants.MUSEUM_WORLD, 
                        new_adv=constants.NEW_ADVENTURES_WORLD
                    )
                )
                for row in await cur.fetchall():
                    data = LevelData.from_row(row)
                    if (data.world, data.id) not in found:
                        found.add((data.world, data.id))
                        levels.append(((data.world, data.id), data))

                # [map_id]
                await cur.execute(
                    '''
                    SELECT * FROM levels 
                    WHERE LOWER(map_id) == LOWER(:map) AND parent IS NULL AND (
                        :f_map IS NULL OR LOWER(map_id) == LOWER(:f_map)
                    ) AND (
                        :f_world IS NULL OR LOWER(world) == LOWER(:f_world)
                    )
                    ORDER BY CASE world 
                        WHEN :default
                        THEN NULL
                        ELSE world
                    END ASC;
                    ''',
                    dict(map=query, f_map=f_map, f_world=f_world, default=constants.BABA_WORLD)
                )
                for row in await cur.fetchall():
                    data = LevelData.from_row(row)
                    if (data.world, data.id) not in found:
                        found.add((data.world, data.id))
                        levels.append(((data.world, data.id), data))
        
        return levels

    @commands.cooldown(5, 8, commands.BucketType.channel)
    @commands.group(name="level", invoke_without_command=True)
    async def level_command(self, ctx: Context, *, query: str):
        '''Renders the Baba Is You level from a search term.

        Levels are searched for in the following order:
        * Custom level code (e.g. "1234-ABCD")
        * World & level ID (e.g. "baba/20level")
        * Level ID (e.g. "16level")
        * Level number (e.g. "space-3" or "lake-extra 1")
        * Level name (e.g. "further fields")
        * The map ID of a world (e.g. "cavern", or "lake")
        '''
        await self.perform_level_command(ctx, query, mobile=False)

    @commands.cooldown(5, 8, commands.BucketType.channel)
    @level_command.command()
    async def mobile(self, ctx: Context, *, query: str):
        '''Renders the mobile Baba Is You level from a search term.

        Levels are searched for in the following order:
        * World & level ID (e.g. "baba/20level")
        * Level ID (e.g. "16level")
        * Level number (e.g. "space-3" or "lake-extra 1")
        * Level name (e.g. "further fields")
        * The map ID of a world (e.g. "cavern", or "lake")
        '''
        await self.perform_level_command(ctx, query, mobile=True)
    
    async def perform_level_command(self, ctx: Context, query: str, *, mobile: bool):
        # User feedback
        await ctx.typing()

        custom_level: CustomLevelData | None = None
        
        spoiler = query.count("||") >= 2
        fine_query = query.lower().strip().replace("|", "")
        
        # [abcd-0123]
        if re.match(r"^[a-z0-9]{4}\-[a-z0-9]{4}$", fine_query) and not mobile:
            row = await self.bot.db.conn.fetchone(
                '''
                SELECT * FROM custom_levels WHERE code == ?;
                ''',
                fine_query
            )
            if row is not None:
                custom_level = CustomLevelData.from_row(row)
            else:
                # Expensive operation 
                await ctx.reply("Searching for custom level... this might take a while", mention_author=False)
                await ctx.typing()
                async with aiohttp.request("GET", f"https://baba-is-bookmark.herokuapp.com/api/level/exists?code={fine_query.upper()}") as resp:
                    if resp.status in (200, 304):
                        data = await resp.json()
                        if data["data"]["exists"]:
                            try:
                                custom_level = await self.bot.get_cog("Reader").render_custom_level(fine_query)
                            except ValueError as e:
                                size = e.args[0]
                                return await ctx.error(f"The level code is valid, but the level's width, height or area is way too big ({size})!")
                            except aiohttp.ClientResponseError as e:
                                return await ctx.error(f"The Baba Is Bookmark site returned a bad response. Try again later.")
        if custom_level is None:
            levels = await self.search_levels(fine_query)
            if len(levels) == 0:
                return await ctx.error("A level could not be found with that query.")
            _, level = levels[0]
        else:
            levels = {}
            level = custom_level

        if isinstance(level, LevelData):
            path = level.unique()
            display = level.display()
            rows = [
                f"Name: ||`{display}`||" if spoiler else f"Name: `{display}`",
                f"ID: `{path}`",
            ]
            if level.subtitle:
                rows.append(
                    f"Subtitle: `{level.subtitle}`"
                )
            mobile_exists = os.path.exists(f"target/renders/{level.world}_m/{level.id}.gif")
            
            if not mobile and mobile_exists:
                rows.append(
                    f"*This level is also on mobile, see `+level mobile {level.unique()}`*"
                )
            elif mobile and mobile_exists:
                rows.append(
                    f"*This is the mobile version. For others, see `+level {level.unique()}`*"
                )

            if mobile and mobile_exists:
                gif = discord.File(f"target/renders/{level.world}_m/{level.id}.gif", spoiler=True)
            elif mobile and not mobile_exists:
                rows.append("*This level doesn't have a mobile version. Using the normal gif instead...*")
                gif = discord.File(f"target/renders/{level.world}/{level.id}.gif", spoiler=True)
            else:
                gif = discord.File(f"target/renders/{level.world}/{level.id}.gif", spoiler=True)
        else:
            gif = discord.File(f"target/renders/levels/{level.code}.gif", spoiler=True)
            path = level.unique()
            display = level.name
            rows = [
                f"Name: ||`{display}`|| (by `{level.author}`)" 
                    if spoiler else f"Name: `{display}` (by `{level.author}`)",
                f"Level code: `{path}`",
            ]
            if level.subtitle:
                rows.append(
                    f"Subtitle: `{level.subtitle}`"
                )

        if len(levels) > 1:
            levels = levels[1:]
            extras = [level.unique() for _, level in levels]
            if len(levels) > constants.OTHER_LEVELS_CUTOFF:
                extras = extras[:constants.OTHER_LEVELS_CUTOFF]
            paths = ", ".join(f"`{extra}`" for extra in extras)
            plural = "result" if len(extras) == 1 else "results"
            suffix = ", `...`" if len(levels) > constants.OTHER_LEVELS_CUTOFF else ""
            rows.append(
                f"*Found {len(levels)} other {plural}: {paths}{suffix}*"
            )

        formatted = "\n".join(rows)

        # Only the author should be mentioned
        mentions = discord.AllowedMentions(everyone=False, users=[ctx.author], roles=False)

        # Send the result
        await ctx.reply(formatted, file=gif, allowed_mentions=mentions)

async def setup(bot: Bot):
    await bot.add_cog(GlobalCog(bot))
