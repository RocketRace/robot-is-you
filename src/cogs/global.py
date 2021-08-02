from __future__ import annotations

import functools
import random
import re
import zipfile
from datetime import datetime
from io import BytesIO
from json import load
from os import listdir
from string import ascii_lowercase
from time import time
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageChops

if TYPE_CHECKING:
    from ..tile import RawGrid

from .. import constants, errors
from ..tile import RawTile
from ..types import Bot, Context


def try_index(string: str, value: str) -> int:
    '''Returns the index of a substring within a string.
    Returns -1 if not found.
    '''
    index = -1
    try:
        index = string.index(value)
    except:
        pass
    return index

# Splits the "text_x,y,z..." shortcuts into "text_x", "text_y", ...
def split_commas(grid: list[list[str]], prefix: str):
    for row in grid:
        to_add = []
        for i, word in enumerate(row):
            if "," in word:
                if word.startswith(prefix):
                    each = word.split(",")
                    expanded = [each[0]]
                    expanded.extend([prefix + segment for segment in each[1:]])
                    to_add.append((i, expanded))
                else:
                    raise errors.SplittingException(word)
        for change in reversed(to_add):
            row[change[0]:change[0] + 1] = change[1]
    return grid

class GlobalCog(commands.Cog, name="Baba Is You"):
    def __init__(self, bot: Bot):
        self.bot = bot
        with open("config/leveltileoverride.json") as f:
            j = load(f)
            self.level_tile_override = j

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
            mode, size = rest
            return await ctx.error(
                f"{msg}, since it's too long ({size}) for '{mode}' mode."
            )
        else:
            return await ctx.error(f"{msg}.")
        

    # @commands.group(invoke_without_command=True)
    # @commands.cooldown(5, 8, commands.BucketType.channel)
    async def make(self, ctx: Context, text: str, color: str = "", style: str = "noun", meta_level: int = 0, direction: str = "none", palette = "default"):
        '''Generates a custom text sprite. 
        
        Use "/" in the text to force a line break.

        The `color` argument can be a hex color (`"#ffffff"`) or a string (`"red"`).

        The `style` argument may be "noun", "property", or "letter".
        
        The `meta_level` argument should be some number, and applies a metatext filter to the sprite. It defaults to 0.

        The `direction` argument may be "none", "right", "up", "left", or "down". 
        This can be used with the "property" style to generate directional properties (such as FALL or NUDGE).

        The `palette` argument can be set to the name of a palette.
        '''
        # These colors are based on the default palette
        if color:
            real_color = color.lower()
            if real_color.startswith("#"): 
                int_color = int(real_color[1:], base=16) & (2 ** 24 - 1)
                byte_color = (int_color >> 16, (int_color & 255 << 8) >> 8, int_color & 255)
                tile_color = (byte_color[0] / 256, byte_color[1] / 256, byte_color[2] / 256)
            elif real_color.startswith("0x"):
                int_color = int(real_color, base=16)
                byte_color = (int_color >> 16, (int_color & 255 << 8) >> 8, int_color & 255)
                tile_color = (byte_color[0] / 256, byte_color[1] / 256, byte_color[2] / 256)
            elif real_color in constants.COLOR_NAMES:
                try:
                    palette_img = Image.open(f"data/palettes/{palette}.png").convert("RGB")
                    color_index = constants.COLOR_NAMES[real_color]
                    tile_color = tuple(p/256 for p in palette_img.getpixel(color_index))
                except FileNotFoundError:
                    return await ctx.error(f"The palette `{palette}` is not valid.")
            else:
                return await ctx.error(f"The color `{color}` is invalid.")
        else:
            tile_color = (1, 1, 1)
        if style not in ("noun", "property", "letter"):
            return await ctx.error(f"The style `{style}` is not valid. it must be one of `noun`, `property` or `letter`.")
        if direction not in ("none", "up", "right", "left", "down"):
            return await ctx.error(f"The direction `{direction}` is not valid. It must be one of `none`, `up`, `right`, `left` or `down`.")
        if "property" == style:
            if direction in ("up", "right", "left", "down"):
                style = style + direction
        if not 0 <= meta_level <= constants.MAX_META_DEPTH:
            return await ctx.error(f"The meta level `{meta_level}` is invalid. It must be one of: " + ", ".join(f"`{n}`" for n in range(constants.MAX_META_DEPTH + 1)) + ".")
        try:
            meta_level = int(meta_level)
            buffer = BytesIO()
            tile = Tile(name=text.lower(), color=tile_color, style=style.lower(), custom=True)
            tile.images = self.generate_tile(tile.name, color=tile.color, style=style, meta_level=meta_level)
            self.render([[[tile]]], 1, 1, out=buffer)
            await ctx.reply(file=discord.File(buffer, filename=f"custom_'{text.replace('/','')}'.gif"))
        except TooManyLineBreaks as e:
            text, count = e.args
            return await ctx.error(f"The text `{text}` could not be generated, because it contains {count} `/` characters (max 1).")
        except LeadingTrailingLineBreaks as e:
            text = e.args[0]
            return await ctx.error(f"The text `{text}` could not be generated, because it starts or ends with a `/` character.")
        except BlankCustomText as e:
            return await ctx.error("The name of a text tile can't be blank. Make sure there aren't any typos in your input.")
        except BadCharacter as e:
            text, char = e.args
            return await ctx.error(f"The text `{text}` could not be generated, because no appropriate letter sprite exists for `{char}`.")
        except CustomTextTooLong as e:
            text, length = e.args
            return await ctx.error(f"The text `{text}` could not be generated, because it is too long ({length}).")
        except BadLetterStyle as e:
            text = e.args[0]
            return await ctx.error(f"The text `{text}` could not be generated, because the `letter` variant can only be used on text that's two letters long.")
        
    # @make.command()
    # @commands.cooldown(5, 8, type=commands.BucketType.channel)
    async def raw(self, ctx: Context, text: str, style: str = "noun", meta_level: int = 0, direction: str = "none"):
        '''Returns a zip archive of the custom tile.

        A raw sprite has no color!

        The `style` argument may be "noun", "property", or "letter".
        
        The `meta_level` argument should be a number.
        '''
        real_text = text.lower()
        if style not in ("noun", "property", "letter"):
            return await ctx.error(f"`{style}` is not a valid style. It must be one of `noun`, `property` or `letter`.")
        if not 0 <= meta_level <= constants.MAX_META_DEPTH:
            return await ctx.error(f"The meta level `{meta_level}` is invalid. It must be one of: " + ", ".join(f"`{n}`" for n in range(constants.MAX_META_DEPTH + 1)) + ".")
        if direction not in ("none", "up", "right", "left", "down"):
            return await ctx.error(f"`{direction}` is not a valid direction. It must be one of `none`, `up`, `right`, `left` or `down`.")
        if style == "property":
            if direction in ("up", "right", "left", "down"):
                style = style + direction
        try:
            meta_level = int(meta_level)
            buffer = BytesIO()
            images = self.generate_tile(real_text, (1, 1, 1), style, meta_level)
            with zipfile.ZipFile(buffer, mode="w") as archive:
                for i, image in enumerate(images):
                    img_buffer = BytesIO()
                    image.save(img_buffer, format="PNG")
                    img_buffer.seek(0)
                    archive.writestr(f"text_{meta_level*'meta_'}{real_text.replace('/','')}_0_{i + 1}.png", data=img_buffer.getbuffer())
            buffer.seek(0)
            await ctx.reply(
                f"*Raw sprites for `text_{meta_level*'meta_'}{real_text.replace('/','')}`*", 
                file = discord.File(buffer, filename=f"custom_{meta_level*'meta_'}{real_text.replace('/','')}_sprites.zip")
            )
        except TooManyLineBreaks as e:
            text, count = e.args
            return await ctx.error(f"The text `{text}` could not be generated, because it contains {count} `/` characters (max 1).")
        except LeadingTrailingLineBreaks as e:
            text = e.args[0]
            return await ctx.error(f"The text `{text}` could not be generated, because it starts or ends with a `/` character.")
        except BlankCustomText as e:
            return await ctx.error("The name of a text tile can't be blank. Make sure there aren't any typos in your input.")
        except BadCharacter as e:
            text, char = e.args
            return await ctx.error(f"The text `{text}` could not be generated, because no appropriate letter sprite exists for `{char}`.")
        except CustomTextTooLong as e:
            text, length = e.args
            return await ctx.error(f"The text `{text}` could not be generated, because it is too long ({length}).")
        except BadLetterStyle as e:
            text = e.args[0]
            return await ctx.error(f"The text `{text}` could not be generated, because the `letter` variant can only be used on text that's two letters long.")

    def parse_raw(self, grid: list[list[list[str]]], *, rule: bool) -> RawGrid:
        '''Parses a string grid into a RawTile grid'''
        return [
            [
                [
                    RawTile.from_str(
                        "-" if tile == "-" else tile[5:] if tile.startswith("tile_") else f"text_{tile}"
                    ) if rule else RawTile.from_str(
                        "-" if tile == "text_-" else tile
                    )
                    for tile in stack
                ]
                for stack in row
            ]
            for row in grid
        ]

    async def render_tiles(self, ctx: Context, *, objects: str, rule: bool):
        '''Performs the bulk work for both `tile` and `rule` commands.'''
        await ctx.trigger_typing()
        start = time()
        tiles = objects.lower().strip().replace("\\", "")

        # Determines if this should be a spoiler
        spoiler = "|" in tiles
        tiles = tiles.replace("|", "")
        
        # Check for empty input
        if not tiles:
            return await ctx.error("Input cannot be blank.")

        # Split input into lines
        word_rows = tiles.splitlines()
        
        # Split each row into words
        word_grid = [row.split() for row in word_rows]

        # Check palette & bg flags
        potential_flags = []
        potential_count = 0
        try:
            for y, row in enumerate(word_grid):
                for x, word in enumerate(row):
                    if potential_count == 2:
                        raise Exception
                    potential_flags.append((word, x, y))
                    potential_count += 1
        except Exception: pass
        background = None
        palette = "default"
        to_delete = []
        for flag, x, y in potential_flags:
            bg_match = re.fullmatch(r"(--background|-b)(=(\d)/(\d))?", flag)
            if bg_match:
                if bg_match.group(3) is not None:
                    tx, ty = int(bg_match.group(3)), int(bg_match.group(4))
                    if not (0 <= tx <= 7 and 0 <= ty <= 5):
                        return await ctx.error("The provided background color is invalid.")
                    background = tx, ty
                else:
                    background = (0, 4)
                to_delete.append((x, y))
                continue
            flag_match = re.fullmatch(r"(--palette=|-p=|palette:)(\w+)", flag)
            if flag_match:
                palette = flag_match.group(2)
                if palette + ".png" not in listdir("data/palettes"):
                    return await ctx.error(f"Could not find a palette with name \"{palette}\".")
                to_delete.append((x, y))
        for x, y in reversed(to_delete):
            del word_grid[y][x]
        
        try:
            if rule:
                comma_grid = split_commas(word_grid, "tile_")
            else:
                comma_grid = split_commas(word_grid, "text_")
        except errors.SplittingException as e:
            cause = e.args[0]
            return await ctx.error(f"I couldn't split the following input into separate objects: \"{cause}\".")

        # Splits "&"-joined words into stacks
        stacked_grid: list[list[list[str]]] = []
        for row in comma_grid:
            stacked_row: list[list[str]] = []
            for stack in row:
                split = stack.split("&")
                stacked_row.append(split)
                if len(split) > constants.MAX_STACK and ctx.author.id != self.bot.owner_id:
                    return await ctx.error(f"Stack too high ({len(split)}).\nYou may only stack up to {constants.MAX_STACK} tiles on one space.")
            stacked_grid.append(stacked_row)


        # Get the dimensions of the grid
        width = max(len(row) for row in stacked_grid)
        height = len(stacked_grid)

        # Don't proceed if the request is too large.
        # (It shouldn't be that long to begin with because of Discord's 2000 character limit)
        area = width * height
        if area > constants.MAX_TILES and ctx.author.id != self.bot.owner_id:
            return await ctx.error(f"Too many tiles ({area}). You may only render up to {constants.MAX_TILES} tiles at once, including empty tiles.")
        elif area == 0:
            return await ctx.error(f"Can't render nothing.")

        # Pad the word rows from the end to fit the dimensions
        for row in stacked_grid:
            row.extend([["-"]] * (width - len(row)))

        grid = self.parse_raw(stacked_grid, rule=rule)
        try:
            # Handles variants based on `:` affixes
            full_grid = self.bot.handlers.handle_grid(grid)
            buffer = BytesIO()
            task = functools.partial(
                self.bot.renderer.render,
                full_grid,
                palette=palette,
                background=background, 
                out=buffer,
                random_animations=True
            )
            await self.bot.loop.run_in_executor(None, task)
        except errors.TileNotFound as e:
            word = e.args[0]
            if word.name.startswith("tile_") and self.bot.get.tile_data(word.name[5:]) is not None:
                return await ctx.error(f"The tile `{word}` could not be found. Perhaps you meant `{word.name[5:]}`?")
            if self.bot.get.tile_data("text_" + word.name) is not None:
                return await ctx.error(f"The tile `{word}` could not be found. Perhaps you meant `{'text_' + word.name}`?")
            return await ctx.error(f"The tile `{word}` could not be found.")
        except errors.BadTileProperty as e:
            word, (w, h) = e.args
            return await ctx.error(f"The tile `{word}` could not be made into a property, because it's too big (`{w} by {h}`).")
        except errors.VariantError as e:
            return await self.handle_variant_errors(ctx, e)
        except errors.TextGenerationError as e:
            return await self.handle_custom_text_errors(ctx, e)

        filename = datetime.utcnow().strftime(r"render_%Y-%m-%d_%H.%M.%S.gif")
        delta = time() - start
        msg = f"*Rendered in {delta:.2f} s*"
        await ctx.reply(content=msg, file=discord.File(buffer, filename=filename, spoiler=spoiler))
        

    @commands.command(aliases=["text"])
    @commands.cooldown(5, 8, type=commands.BucketType.channel)
    async def rule(self, ctx: Context, *, objects: str = ""):
        '''Renders the text tiles provided. 
        
        If not found, the bot tries to auto-generate them! (See the `make` command for more.)

        **Flags**
        * `--palette=<...>` (`-P=<...>`): Recolors the output gif. See the `palettes` command for more.
        * `--background` (`-B`): Enables background color.
        
        **Variants**
        * `:variant`: Append `:variant` to a tile to change color or sprite of a tile. See the `variants` command for more.

        **Useful tips:**
        * `-` : Shortcut for an empty tile. 
        * `&` : Stacks tiles on top of each other.
        * `tile_` : `tile_object` renders regular objects.
        * `,` : `tile_x,y,...` is expanded into `tile_x tile_y ...`
        * `||` : Marks the output gif as a spoiler. 
        
        **Example commands:**
        `rule baba is you`
        `rule -B rock is ||push||`
        `rule -P=test tile_baba on baba is word`
        `rule baba eat baba - tile_baba tile_baba:l`
        '''
        await self.render_tiles(ctx, objects=objects, rule=True)

    # Generates an animated gif of the tiles provided, using the default palette
    @commands.command()
    @commands.cooldown(5, 8, type=commands.BucketType.channel)
    async def tile(self, ctx: Context, *, objects: str = ""):
        '''Renders the tiles provided.

       **Flags**
        * `--palette=<...>` (`-P=<...>`): Recolors the output gif. See the `palettes` command for more.
        * `--background=[...]` (`-B=[...]`): Enables background color. If no argument is given, defaults to black. The argument must be a palette index ("x/y").
        
        **Variants**
        * `:variant`: Append `:variant` to a tile to change color or sprite of a tile. See the `variants` command for more.

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
        await self.render_tiles(ctx, objects=objects, rule=False)

    @commands.cooldown(5, 8, commands.BucketType.channel)
    @commands.command(name="level")
    async def _level(self, ctx: Context, *, query: str):
        '''Renders the given Baba Is You level.

        Levels are searched for in the following order:
        * Checks if the input matches a custom level code (e.g. "1234-ABCD")
        * Checks if the input matches a level ID (e.g. "20level")
        * Checks if the input matches a level number (e.g. "space-3" or "lake-extra 1")
        * Checks if the input matches a level name (e.g. "further fields")
        * Checks if the input is the ID of a world (e.g. "cavern")
        '''
        # User feedback
        await ctx.trigger_typing()

        levels = {}
        custom = False
        # Lower case, make the query all nice
        spoiler = query.count("||") >= 2
        fine_query = query.lower().strip().replace("|", "")
        # Is it the level ID?
        level_data = self.bot.get_cog("Reader").level_data
        if level_data.get(fine_query) is not None:
            levels[fine_query] = level_data[fine_query]

        # Check custom level from cache
        if len(levels) == 0:
            upper = fine_query.upper()
            if re.match(r"^[A-Z0-9]{4}\-[A-Z0-9]{4}$", upper):
                custom_levels = self.bot.get_cog("Reader").custom_levels
                if custom_levels.get(upper) is not None:
                    levels[upper] = custom_levels[upper]
                    custom = True
                else:
                    await ctx.reply("Searching for custom level... this might take a while", mention_author=False)
                    await ctx.trigger_typing()
                    async with aiohttp.request("GET", f"https://baba-is-bookmark.herokuapp.com/api/level/exists?code={upper}") as resp:
                        if resp.status in (200, 304):
                            data = await resp.json()
                            if data["data"]["exists"]:
                                try:
                                    levels[upper] = await self.bot.get_cog("Reader").render_custom(upper)
                                    custom = True
                                except ValueError as e:
                                    size = e.args[0]
                                    return await ctx.error(f"The level code is valid, but the leve's width, height or area is way too big ({size})!")
                                except aiohttp.ClientResponseError as e:
                                    return await ctx.error(f"The Baba Is Bookmark site returned a bad response. Try again later.")


        # Does the query match a level tree?
        if len(levels) == 0:
            # Separates the map and the number / letter / extra number from the query.
            tree = [string.strip() for string in fine_query.split("-")]
            # There should only be two parts to the query.
            if len(tree) == 2:
                # The two parts
                map_id = tree[0]
                identifier = tree[1]
                # What style of level identifier are we given?
                # Style: 0 -> "extra" + number
                # Style: 1 -> number
                # Style: 2 -> letter
                style = None
                # What "number" is the level?
                # .ld files use "number" to refer to both numbers, letters and extra numbers.
                number = None
                if identifier.isnumeric():
                    # Numbers
                    style = 0
                    number = int(identifier)
                elif len(identifier) == 1 and identifier.isalpha():
                    # Letters (only 1 letter)
                    style = 1
                    # 0 <--> a
                    # 1 <--> b
                    # ...
                    # 25 <--> z
                    raw_number = try_index(ascii_lowercase, identifier)
                    # If the identifier is a lowercase letter, set "number"
                    if raw_number != -1:
                        number = raw_number
                elif identifier.startswith("extra") and identifier[5:].strip().isnumeric():
                    # Extra numbers:
                    # Starting with "extra", ending with numbers
                    style = 2
                    number = int(identifier[5:].strip()) - 1
                else:
                    number = identifier
                    style = -1
                if style is not None and number is not None:
                    # Custom map ID?
                    if style == -1:
                        # Check for the map ID & custom identifier combination
                        for filename,data in level_data.items():
                            if data["map_id"] == number and data["parent"] == map_id:
                                levels[filename] = data
                    else:
                        # Check for the map ID & identifier combination
                        for filename,data in level_data.items():
                            if data["style"] == style and data["number"] == number and data["parent"] == map_id:
                                levels[filename] = data

        # Is the query a real level name?
        if len(levels) == 0:
            for filename,data in level_data.items():
                # Matches an existing level name
                if data["name"] == fine_query:
                    # Guaranteed
                    levels[filename] = data

        # Map ID?
        if len(levels) == 0:
            for filename,data in level_data.items():
                if data["map_id"] == fine_query and data["parent"] is None:
                    levels[filename] = data

        # If not found: error message
        if len(levels) == 0:
            return await ctx.error(f'Could not find a level matching the query `{fine_query}`.')

        # If found:
        else:
            # Is there more than 1 match?
            matches = len(levels)

            level_id, level = [*levels.items()][0]
            # 'source', 'name', 'subtitle'? checked for both vanilla & custom
            # 'parent', 'map_id', 'style', 'number' checked for vanilla

            # The embedded file
            gif = discord.File(f"target/renders/{level['source']}/{level_id}.gif", spoiler=True)
            
            # Level name
            name = level["name"]

            # Level parent 
            if not custom:
                parent = level.get("parent")
                map_id = level.get("map_id")
                tree = ""
                # Parse the display name
                if parent is not None:
                    # With a custom map id
                    if map_id is not None:
                        # Format
                        tree = parent + "-" + map_id + ": "
                    else:
                        # Parse the level style
                        style = level["style"]
                        number = level["number"]
                        identifier = None
                        # Regular numbers
                        if style == 0:
                            identifier = number
                        elif style == 1:
                        # Letters
                            identifier = ascii_lowercase[int(number)]
                        elif style == 2:
                        # Extra dots
                            identifier = "extra " + str(int(number) + 1)
                        else: 
                        # In case the custom map ID wasn't already set
                            identifier = map_id
                        # format
                        tree = f"{parent}-{identifier}: "
            
            if custom:
                author = f"\nAuthor: `{level['author']}`"

            # Level subtitle, if any
            subtitle = ""
            if level.get("subtitle") and level.get("subtitle").strip():
                subtitle = "\nSubtitle: `" + level["subtitle"] + "`"

            # Any additional matches
            matches_text = "" if matches == 1 else f"\nFound {matches} matches: `{', '.join([l for l in levels])}`, showing the first." 

            # Formatted output
            if custom:
                if spoiler:
                    wrapped_name = f"||`{name}`||"
                else:
                    wrapped_name = f"`{name}`"
                formatted = f"{matches_text} (Custom Level)\nName: {wrapped_name}\nCode: `{level_id}`{author}{subtitle}"
            else:
                if spoiler:
                    wrapped_name = f"||`{tree}{name}`||"
                else:
                    wrapped_name = f"`{tree}{name}`"
                formatted = f"{matches_text}\nName: {wrapped_name}\nID: `{level_id}`{subtitle}"

            # Only the author should be mentioned
            mentions = discord.AllowedMentions(everyone=False, users=[ctx.author], roles=False)

            # Send the result
            await ctx.reply(formatted, file=gif, allowed_mentions=mentions)

def setup(bot: Bot):
    bot.add_cog(GlobalCog(bot))
