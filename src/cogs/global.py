from __future__ import annotations

import functools
import random
import re
import zipfile
from datetime import datetime
from inspect import Parameter
from io import BytesIO
from json import load
from os import listdir
from string import ascii_lowercase
from time import time
from typing import BinaryIO

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageChops, ImageDraw, ImageFilter
from ..utils import Tile, cached_open, constants
from .types import Bot, Context

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

class SplittingException(ValueError):
    pass

class BadMetaLevel(ValueError):
    pass

class BadPaletteIndex(ValueError):
    pass

class NotFound(ValueError):
    pass

class BadTilingVariant(ValueError):
    pass

class TooManyLineBreaks(ValueError):
    pass

class LeadingTrailingLineBreaks(ValueError):
    pass

class BlankCustomText(ValueError):
    pass

class BadCharacter(ValueError):
    pass

class CustomTextTooLong(ValueError):
    pass

class BadLetterStyle(ValueError):
    pass

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
                    raise SplittingException(word)
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

    def save_frames(self, frames: list[Image.Image], fp: str | BinaryIO):
        '''Saves a list of images as a gif to the specified file path.'''
        frames[0].save(fp, "GIF",
            save_all=True,
            append_images=frames[1:],
            loop=0,
            duration=200,
            disposal=2, # Frames don't overlap
            transparency=255,
            background=255,
            optimize=False # Important in order to keep the color palettes from being unpredictable
        )
        if not isinstance(fp, str): fp.seek(0)

    def make_meta(self, name: str, img: Image.Image, meta_level: int) -> Image.Image:
        if meta_level > constants.max_meta_depth:
            raise BadMetaLevel(name, meta_level)
        elif meta_level == 0:
            return img

        original = img.copy()
        final = img
        for i in range(meta_level):
            _, _, _, alpha = final.convert("RGBA").split()
            base = Image.new("L", (final.width + 6, final.width + 6))
            base.paste(final, (3, 3), alpha)
            base = ImageChops.invert(base)
            base = base.filter(ImageFilter.FIND_EDGES)
            ImageDraw.floodfill(base, (0, 0), 0, 0)
            base = base.crop((2, 2, base.width - 2, base.height - 2))
            base = base.convert("1")
            final = base.convert("RGBA")
            final.putalpha(base)
        if meta_level >= 2 and meta_level % 2 == 0:
            final.paste(original, (i + 1, i + 1), original.convert("L"))
        elif meta_level >= 2 and meta_level % 2 == 1:
            final.paste(ImageChops.invert(original), (i + 1, i + 1), original.convert("L"))
        
        return final
        

    def render(
        self,
        word_grid: list[list[list[Tile]]],
        width: int,
        height: int,
        *,
        palette: str = "default",
        images: list[Image.Image] | None = None,
        image_source: str = "vanilla",
        out: str = "target/renders/render.gif",
        background: tuple[int, int] | None = None,
        rand: bool = False,
        use_overridden_colors: bool = False
    ):
        '''Takes a list of Tile objects and generates a gif with the associated sprites.

        out is a file path or buffer. Renders will be saved there, otherwise to `target/renders/render.gif`.

        palette is the name of the color palette to refer to when rendering.

        images is a list of background image filenames. Each image is retrieved from `data/images/{imageSource}/image`.

        background is a palette index. If given, the image background color is set to that color, otherwise transparent. Background images overwrite this. 
        '''
        frames = []
        palette_img = Image.open(f"data/palettes/{palette}.png").convert("RGB")

        # Calculates padding based on image sizes
        left_pad = 0
        right_pad = 0
        up_pad = 0
        down_pad = 0

        # Get sprites to be pasted
        cache= {}
        imgs = []
        for frame in range(3):
            temp_frame = []
            for y, row in enumerate(word_grid):
                temp_row = []
                for x, stack in enumerate(row):
                    temp_stack = []
                    for _z, tile in enumerate(stack):
                        if tile.name is None:
                            continue
                        # Custom tiles
                        if tile.custom:
                            # Custom tiles are already rendered, and have their meta level applied properly
                            img = tile.images[frame]
                            if y == 0:
                                diff = img.size[1] - 24
                                if diff > up_pad:
                                    up_pad = diff
                            if y == len(word_grid) - 1:
                                diff = img.size[1] - 24
                                if diff > down_pad:
                                    down_pad = diff
                            if x == 0:
                                diff = img.size[0] - 24
                                if diff > left_pad:
                                    left_pad = diff
                            if x == len(row) - 1:
                                diff = img.size[0] - 24
                                if diff > right_pad:
                                    right_pad = diff
                            temp_stack.append(img)
                            continue
                        if rand:
                            # Random animations
                            animation_offset = (hash(x + y) + frame) % 3
                        else:
                            animation_offset = frame
                        # Certain sprites have to be hard-coded, since their file paths are not very neat
                        if tile.name in ("icon",):
                            path = f"data/sprites/vanilla/{tile.name}.png"
                        elif tile.name in ["smiley", "hi"] or tile.name.startswith("icon"):
                            path = f"data/sprites/vanilla/{tile.name}_1.png"
                        elif tile.name == "default":
                            path = f"data/sprites/vanilla/default_{animation_offset + 1}.png"
                        else:
                            maybe_sprite = self.bot.get_cog("Admin").tile_data.get(tile.name).get("sprite")
                            if maybe_sprite != tile.name:
                                path = f"data/sprites/{tile.source}/{maybe_sprite}_{tile.variant}_{animation_offset + 1}.png"
                            else:
                                path = f"data/sprites/{tile.source}/{tile.name}_{tile.variant}_{animation_offset + 1}.png"
                        if tile.color is None:
                            base = None
                            if use_overridden_colors:
                                base = self.level_tile_override.get(tile.name)
                            base = base if base is not None else self.bot.get_cog("Admin").tile_data[tile.name]
                            tile.color = base.get("active")
                            if tile.color is None:
                                tile.color = base.get("color")
                            tile.color = tuple(map(int, tile.color))
                        img = cached_open(path, cache=cache, is_image=True).convert("RGBA")
                        img = self.make_meta(tile.name, img, tile.meta_level)
                        c_r, c_g, c_b = palette_img.getpixel(tile.color)
                        _r, _g, _b, a = img.split()
                        color_matrix = (c_r / 256, 0, 0, 0,
                                        0, c_g / 256, 0, 0,
                                    0, 0, c_b / 256, 0)
                        img = img.convert("RGB").convert("RGB", matrix=color_matrix)
                        img.putalpha(a)
                        temp_stack.append(img)
                        # Check image sizes and calculate padding
                        if y == 0:
                            diff = img.size[1] - 24
                            if diff > up_pad:
                                up_pad = diff
                        if y == len(word_grid) - 1:
                            diff = img.size[1] - 24
                            if diff > down_pad:
                                down_pad = diff
                        if x == 0:
                            diff = img.size[0] - 24
                            if diff > left_pad:
                                left_pad = diff
                        if x == len(row) - 1:
                            diff = img.size[0] - 24
                            if diff > right_pad:
                                right_pad = diff
                    temp_row.append(temp_stack)
                temp_frame.append(temp_row)
            imgs.append(temp_frame)

         
        for i,frame in enumerate(imgs):
            # Get new image dimensions, with appropriate padding
            total_width = len(frame[0]) * 24 + left_pad + right_pad 
            total_height = len(frame) * 24 + up_pad + down_pad 

            # Montage image
            # bg images
            if bool(images) and image_source is not None:
                render_frame = Image.new("RGBA", (total_width, total_height))
                # for loop in case multiple background images are used (i.e. baba's world map)
                for image in images:
                    overlap = Image.open(f"data/images/{image_source}/{image}_{i + 1}.png") # i + 1 because 1-indexed
                    mask = overlap.getchannel("A")
                    render_frame.paste(overlap, mask=mask)
            # bg color
            elif background is not None:
                palette_img = Image.open(f"data/palettes/{palette}.png").convert("RGB") # ensure alpha channel exists, even if blank
                palette_color = palette_img.getpixel(background)
                render_frame = Image.new("RGBA", (total_width, total_height), color=palette_color)
            # neither
            else: 
                render_frame = Image.new("RGBA", (total_width, total_height))

            # Pastes each image onto the frame
            # For each row
            y_offset = up_pad # For padding: the cursor for example doesn't render fully when alone
            for row in frame:
                # For each image
                x_offset = left_pad # Padding
                for stack in row:
                    for tile in stack:
                        if tile is not None:
                            if isinstance(tile, list):
                                elem = tile[i]
                            else:
                                elem = tile

                            width = elem.width
                            height = elem.height
                            # For tiles that don't adhere to the 24x24 sprite size
                            offset = (x_offset + (24 - width) // 2, y_offset + (24 - height) // 2)

                            render_frame.paste(elem, offset, elem)
                    x_offset += 24
                y_offset += 24

            # Resizes to 200%
            render_frame = render_frame.resize((2 * total_width, 2 * total_height), resample=Image.NEAREST)
            # Saves the final image
            frames.append(render_frame)

        self.save_frames(frames, out)

    def handle_variants(self, grid: list[list[list[str]]], *, tile_borders: bool = False, is_level: bool = False, palette: str = "default") -> list[list[list[Tile]]]:
        '''Appends variants to tiles in a grid.

        Returns a grid of `Tile` objects.

        * No variant -> "0" sprite variant, default color
        * Shortcut sprite variant -> The associated sprite variant
        * Given sprite variant -> Same sprite variant
        * Sprite variants for a tiling object -> Sprite variant auto-generated according to adjacent tiles
        * Shortcut color variant -> Associated color index 
        * (Source based on tile)
        If tile_borders is given, sprite variants depend on whether the tile is adjacent to the edge of the image.
        '''

        width = len(grid[0])
        height = len(grid)
        palette_img = Image.open(f"data/palettes/{palette}.png").convert("RGB")

        clone_grid = [[[word for word in stack] for stack in row] for row in grid]
        for y, row in enumerate(clone_grid):
            for x, stack in enumerate(row):
                for z, word in enumerate(stack):
                    tile = word
                    final = Tile()
                    if tile in ("-", "empty"):
                        grid[y][x][z] = final
                    else:
                        # Get variants from string
                        if ":" in tile:
                            segments = tile.split(":")
                            tile = segments[0]
                            final.name = tile
                            variants = segments[1:]
                        else:
                            variants = []
                            final.name = word
                        # Easter egg
                        if "hide" in variants:
                            grid[y][x][z] = Tile()
                            continue
                        
                        # Certain tiles from levels are overridden with other tiles
                        tile_data = self.bot.get_cog("Admin").tile_data.get(tile)
                        if is_level:
                            if self.level_tile_override.get(tile) is not None:
                                tile_data = self.level_tile_override[tile]

                        # Apply globally valid variants
                        delete = []
                        for i, variant in enumerate(variants):
                            # COLORS
                            if constants.valid_colors.get(variant) is not None:
                                final.color = constants.valid_colors.get(variant)
                                delete.append(i)
                            elif '/' in variant:
                                try:
                                    tx, ty = tuple(map(int, variant.split('/')))
                                    assert 0 <= tx <= 7
                                    assert 0 <= ty <= 5
                                    final.color = tx,ty
                                    delete.append(i)
                                except AssertionError:
                                    raise BadPaletteIndex(word, variant)
                            # META SPRITES
                            elif variant in ("meta", "m"):
                                final.meta_level += 1
                                delete.append(i)
                            else:
                                match = re.fullmatch(r"m(\d)", variant)
                                if match:
                                    level = int(match.group(1))
                                    if level > constants.max_meta_depth:
                                        raise BadMetaLevel(tile, level)
                                    final.meta_level = level
                                    delete.append(i)
                        delete.reverse()
                        for i in delete:
                            variants.pop(i)
                        
                        # This needs to be evaluated after color variants, so it can compute the proper inactive color
                        if variants.count("inactive") > 0:
                            # If an active variant exists, the default color is inactive
                            for i in range(variants.count("inactive")):
                                if tile_data and tile_data.get("active"):
                                    if final.color is None or tile_data["color"] == final.color:
                                        final.color = tuple(map(int, tile_data["color"]))
                                    else:
                                        final.color = constants.inactive_colors[final.color or (0, 3)]
                                    variants.remove("inactive")
                                elif tile_data:
                                    if final.color is None:
                                        final.color = tuple(map(int, tile_data["color"]))
                                    final.color = constants.inactive_colors[final.color or (0, 3)]
                                    variants.remove("inactive")
                                else:
                                    final.color = constants.inactive_colors[final.color or (0, 3)]
                                    variants.remove("inactive")
                                    

                        # Force custom-rendered text
                        # This has to be rendered beforehand (each sprite can't be generated separately)
                        # because generated sprites uses randomly picked letters
                        if tile_data is None or any(x in variants for x in ("property","noun", "letter")):
                            if tile.startswith("text_"):
                                final.custom = True
                                if "property" in variants:
                                    if "right" in variants or "r" in variants:
                                        final.style = "propertyright"
                                    elif "up" in variants or "u" in variants:
                                        final.style = "propertyup"
                                    elif "left" in variants or "l" in variants:
                                        final.style = "propertyleft"
                                    elif "down" in variants or "d" in variants:
                                        final.style = "propertydown"
                                    else:
                                        final.style = "property"
                                if "noun" in variants:
                                    final.style = "noun"
                                if "letter" in variants:
                                    final.style = "letter"
                                if final.color is None:
                                    # Seed used for RNG to ensure that two identical sprites get generated the same way regardless of stack position
                                    final.images = self.generate_tile(tile[5:], (1,1,1), final.style, final.meta_level, y*100+x) 
                                else:
                                    whites = self.generate_tile(tile[5:], (1,1,1), final.style, final.meta_level, y*100+x)
                                    colored = []
                                    for im in whites:
                                        c_r, c_g, c_b = palette_img.getpixel(final.color)
                                        _r, _g, _b, a = im.split()
                                        color_matrix = (c_r / 256, 0, 0, 0,
                                                        0, c_g / 256, 0, 0,
                                                    0, 0, c_b / 256, 0)
                                        color = im.convert("RGB").convert("RGB", matrix=color_matrix)
                                        color.putalpha(a)
                                        colored.append(color)
                                    final.images = colored
                                grid[y][x][z] = final
                                continue
                            raise NotFound(tile)

                        # Tiles from here on are guaranteed to exist
                        final.source = tile_data.get("source") or "vanilla"

                        tiling = tile_data.get("tiling")
                        direction = 0
                        animation_frame = 0
                        
                        # Is this a tiling object (e.g. wall, water)?
                        if tiling == "1":
                            #  The final variation of the tile
                            out = 0

                            # Tiles that join together
                            def does_tile(stack):
                                return any(t == tile or t == "level" for t in stack)

                            # Is there the same tile adjacent right?
                            if x != width - 1:
                                # The tiles right of this (with variants stripped)
                                adjacent_right = [t.split(":")[0] for t in clone_grid[y][x + 1]]
                                if does_tile(adjacent_right):
                                    out += 1
                            if tile_borders:
                                if x == width - 1:
                                    out += 1

                            # Is there the same tile adjacent above?
                            if y != 0:
                                adjacent_up = [t.split(":")[0] for t in clone_grid[y - 1][x]]
                                if does_tile(adjacent_up):
                                    out += 2
                            if tile_borders:
                                if y == 0:
                                    out += 2

                            # Is there the same tile adjacent left?
                            if x != 0:
                                adjacent_left = [t.split(":")[0] for t in clone_grid[y][x - 1]]
                                if does_tile(adjacent_left):
                                    out += 4
                            if tile_borders:
                                if x == 0:
                                    out += 4

                            # Is there the same tile adjacent below?
                            if y != height - 1:
                                adjacent_down = [t.split(":")[0] for t in clone_grid[y + 1][x]]
                                if does_tile(adjacent_down):
                                    out += 8
                            if tile_borders:
                                if y == height - 1:
                                    out += 8
                            
                            # Stringify
                            final.variant = str(out)
                            if is_level: 
                                grid[y][x][z] = final
                                continue

                        # Apply actual sprite variants
                        for variant in variants:
                            # SPRITE VARIANTS
                            # TODO: clean this up big time
                            if tiling == "-1":
                                if variant in ("r", "right"):
                                    direction = 0
                                elif variant == "0":
                                    final.variant = variant
                                elif is_level:
                                    direction = 0
                                else:
                                    raise BadTilingVariant(word, tiling, variant)
                            elif tiling == "0":
                                if variant in ("r", "right"):
                                    direction = 0
                                elif variant in ("u", "up"):
                                    direction = 1
                                elif variant in ("l", "left"):
                                    direction = 2
                                elif variant in ("d", "down"):
                                    direction = 3
                                elif variant in ( "0", "8", "16", "24"):
                                    final.variant = variant
                                elif is_level:
                                    direction = 0
                                else:
                                    raise BadTilingVariant(word, tiling, variant)
                            elif tiling == "1":
                                if variant in (
                                    "0", "1", "2", "3",
                                    "4", "5", "6", "7",
                                    "8", "9", "10", "11",
                                    "12", "13", "14", "15",
                                ):
                                    final.variant = variant
                                elif is_level:
                                    direction = 0
                                else:
                                    raise BadTilingVariant(word, tiling, variant)
                            elif tiling == "2":
                                if variant in ("r", "right"):
                                    direction = 0
                                elif variant in ("u", "up"):
                                    direction = 1
                                elif variant in ("l", "left"):
                                    direction = 2
                                elif variant in ("d", "down"):
                                    direction = 3
                                elif variant == "a0": 
                                    animation_frame = 0
                                elif variant == "a1": 
                                    animation_frame = 1
                                elif variant == "a2": 
                                    animation_frame = 2
                                elif variant == "a3": 
                                    animation_frame = 3
                                elif variant in ("s", "sleep"): 
                                    animation_frame = -1
                                elif variant in (
                                    "31", "0", "1", "2", "3", 
                                    "7", "8", "9", "10", "11",
                                    "15", "16", "17", "18", "19",
                                    "23", "24", "25", "26", "27",
                                ): 
                                    final.variant = variant
                                elif is_level:
                                    direction = 0
                                else:
                                    raise BadTilingVariant(word, tiling, variant)
                            elif tiling == "3":
                                if variant in ("r", "right"):
                                    direction = 0
                                elif variant in ("u", "up"):
                                    direction = 1
                                elif variant in ("l", "left"):
                                    direction = 2
                                elif variant in ("d", "down"):
                                    direction = 3
                                elif variant == "a1": 
                                    animation_frame = 1
                                elif variant == "a2": 
                                    animation_frame = 2
                                elif variant == "a3": 
                                    animation_frame = 3
                                elif variant in (
                                    "0", "1", "2", "3", 
                                    "8", "9", "10", "11",
                                    "16", "17", "18", "19",
                                    "24", "25", "26", "27",
                                ): 
                                    final.variant = variant
                                elif is_level:
                                    direction = 0
                                else:
                                    raise BadTilingVariant(word, tiling, variant)
                            elif tiling == "4":
                                if variant in ("r", "right"):
                                    direction = 0
                                elif variant == "a1": 
                                    animation_frame = 1
                                elif variant == "a2": 
                                    animation_frame = 2
                                elif variant == "a3": 
                                    animation_frame = 3
                                elif variant in (
                                    "0", "1", "2", "3", 
                                ):
                                    final.variant = variant
                                elif is_level:
                                    direction = 0
                                else:
                                    raise BadTilingVariant(word, tiling, variant)

                        # Compute the final variant, if not already set
                        final.variant = final.variant or (8 * direction + animation_frame) % 32

                        # Finally, push the sprite to the grid
                        grid[y][x][z] = final
        return grid

    @commands.group(invoke_without_command=True)
    @commands.cooldown(5, 8, commands.BucketType.channel)
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
            elif real_color in constants.valid_colors:
                try:
                    palette_img = Image.open(f"data/palettes/{palette}.png").convert("RGB")
                    color_index = constants.valid_colors[real_color]
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
        if not 0 <= meta_level <= constants.max_meta_depth:
            return await ctx.error(f"The meta level `{meta_level}` is invalid. It must be one of: " + ", ".join(f"`{n}`" for n in range(constants.max_meta_depth + 1)) + ".")
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
        
    @make.command()
    @commands.cooldown(5, 8, type=commands.BucketType.channel)
    async def raw(self, ctx: Context, text: str, style: str = "noun", meta_level: int = 0, direction: str = "none"):
        '''Returns a zip archive of the custom tile.

        A raw sprite has no color!

        The `style` argument may be "noun", "property", or "letter".
        
        The `meta_level` argument should be a number.
        '''
        real_text = text.lower()
        if style not in ("noun", "property", "letter"):
            return await ctx.error(f"`{style}` is not a valid style. It must be one of `noun`, `property` or `letter`.")
        if not 0 <= meta_level <= constants.max_meta_depth:
            return await ctx.error(f"The meta level `{meta_level}` is invalid. It must be one of: " + ", ".join(f"`{n}`" for n in range(constants.max_meta_depth + 1)) + ".")
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

    def generate_tile(self, text: str, color: tuple[int, int, int], style: str, meta_level: int, seed: int | None = None) -> list[Image.Image]:
        '''
        Custom tile => rendered custom tile
        '''
        if seed is not None:
            random.seed(seed)
        clean = text.replace("/", "")
        forced = len(clean) != len(text)
        size = len(clean)
        final_arrangement = None
        if text.count("/") >= 2:
            raise TooManyLineBreaks(text, text.count("/"))
        elif text.startswith("/") or text.endswith("/"):
            raise LeadingTrailingLineBreaks(text)

        if size == 0:
            raise BlankCustomText()
        if size == 1:
            if text.isascii() and (text.isalnum() or text == "*"):
                paths = [
                    f"data/sprites/{'vanilla' if text.isalnum() else 'misc'}/text_{text}_0".replace("*", "asterisk")
                ]
                positions = [
                    (12, 12)
                ]
            else:
                raise BadCharacter(text, text)
        elif size == 2 and style == "letter":
            for c in text:
                if not c.isascii() and not c.isalnum() and c not in "~*":
                    raise BadCharacter(text, c)
            paths = [
                f"target/letters/thick/text_{text[0]}_0".replace("*", "asterisk"),
                f"target/letters/thick/text_{text[1]}_0".replace("*", "asterisk"),
            ]
            positions = [
                (6, 12),
                (18, 12)
            ]
        elif size > 10:
            raise CustomTextTooLong(text, size)
        elif style == "letter":
            raise BadLetterStyle(text)
        else:
            if size <= 3 and not forced:
                scale = "big"
                data = self.bot.get_cog("Admin").letter_widths["big"]
                # Attempt to have 1 pixel gaps between letters
                arrangement = [24 // size] * size
                positions = [(int(24 // size * (pos + 0.5)), 11) for pos in range(size)]
            else:
                scale = "small"
                data = self.bot.get_cog("Admin").letter_widths["small"]
                if forced:
                    split = [text.index("/"), len(clean) - text.index("/")]
                else:
                    # Prefer more on the top
                    split = [(size + 1) // 2, size // 2]
                arrangement = [24 // split[0]] * split[0] + [24 // split[1]] * split[1]
                positions = [(int(24 // split[0] * (pos + 0.5)), 6) for pos in range(split[0])] + \
                    [(int(24 // split[1] * (pos + 0.5)), 18) for pos in range(split[1])]
            try:
                widths = {x: data[x] for x in clean}
            except KeyError as e:
                raise BadCharacter(text, e.args[0])
            
            final_arrangement = []
            for char, limit in zip(clean, arrangement):
                top = 0
                second = 0
                for width in widths[char]:
                    if top <= width <= limit:
                        second = top
                        top = width
                if top == 0:
                    raise CustomTextTooLong(text, len(text))
                # Add some variety into the result,
                # in case there is only one sprite of the "ideal" width
                if random.randint(0, 1) and second:
                    final_arrangement.append(second)
                else:
                    final_arrangement.append(top)

            paths = [
                f"target/letters/{scale}/{char}/{width}/" + \
                    random.choice(sorted([
                        i for i in listdir(f"target/letters/{scale}/{char}/{width}") if i.endswith("0.png")
                    ]))[:-6]
                for char, width in zip(clean, final_arrangement)
            ]
        # Special cases and flags everywhere...
        # No wonder nobody wants to work on this code (including myself)
        # gross
        if size == 2 and style != "letter":
            a, b = final_arrangement # trust me here, pylance
            n_a = 11 - a // 2 if a < 12 else 6
            n_b = 13 + b // 2 if b < 12 else 18
            positions = [(n_a, 11), (n_b, 11)] # center the letters

        
        images = []
        for frame in range(3):
            letter_sprites = [
                Image.open(f"{path}_{frame + (size == 1 or style == 'letter')}.png")
                for path in paths
            ]
            letter_sprites = [
                s.getchannel("A") if s.mode == "RGBA" else s.convert("1")
                for s in letter_sprites
            ]
            offset_x, offset_y = 0,0
            if style and "property" in style:
                plate = Image.open(f"data/plates/plate_{style}_0_{frame+1}.png").convert("1")
                base = Image.new("1", plate.size, color=0)
                base = ImageChops.invert(ImageChops.add(base, plate))
                offset_x = (plate.width - 24) // 2
                offset_y = (plate.height - 24) // 2
            else:
                base = Image.new("1", (24, 24), color=0)
            for (x, y), sprite in zip(positions, letter_sprites):
                s_x, s_y = sprite.size
                base.paste(sprite, box=(x - s_x // 2 + offset_x, y - s_y // 2 + offset_y), mask=sprite)

            if style and "property" in style:
                base = ImageChops.invert(base)

            base = self.make_meta(clean, base, meta_level).convert("L")

            # Cute alignment
            color_matrix = (color[0], 0, 0, 0,
                         0, color[1], 0, 0,
                      0, 0, color[2], 0,)

            alpha = base.copy()
            base = base.convert("RGB")
            base = base.convert("RGB", matrix=color_matrix)
            base.putalpha(alpha)
            images.append(base)
        
        return images

    async def render_tiles(self, ctx: Context, *, objects: str, rule: bool):
        '''Performs the bulk work for both `tile` and `rule` commands.'''
        async with ctx.typing():
            tiles = objects.lower().strip().replace("\\", "")
            if tiles == "":
                param = Parameter("objects", Parameter.KEYWORD_ONLY)
                raise commands.MissingRequiredArgument(param)

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
            except: pass
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
                    word_grid = split_commas(word_grid, "tile_")
                else:
                    word_grid = split_commas(word_grid, "text_")
            except SplittingException as e:
                source_of_exception = e.args[0]
                return await ctx.error(f"I couldn't split the following input into separate objects: \"{source_of_exception}\".")

            # Splits "&"-joined words into stacks
            for row in word_grid:
                for i,stack in enumerate(row):
                    if "&" in stack:
                        row[i] = stack.split("&")
                    else:
                        row[i] = [stack]
                    # Limit how many tiles can be rendered in one space
                    height = len(row[i])
                    if height > constants.max_stack and ctx.author.id != self.bot.owner_id:
                        return await ctx.error(f"Stack too high ({height}).\nYou may only stack up to {constants.max_stack} tiles on one space.")

            # Prepends "text_" to words if invoked under the rule command
            if rule:
                word_grid = [[["-" if word == "-" else word[5:] if word.startswith("tile_") else "text_" + word for word in stack] for stack in row] for row in word_grid]
            else:
                word_grid = [[["-" if word in ("-", "text_-") else word for word in stack] for stack in row] for row in word_grid]

            # Get the dimensions of the grid
            lengths = [len(row) for row in word_grid]
            width = max(lengths)
            height = len(word_rows)

            # Don't proceed if the request is too large.
            # (It shouldn't be that long to begin with because of Discord's 2000 character limit)
            area = width * height
            if area > constants.max_tiles and ctx.author.id != self.bot.owner_id:
                return await ctx.error(f"Too many tiles ({area}). You may only render up to {constants.max_tiles} tiles at once, including empty tiles.")
            elif area == 0:
                return await ctx.error(f"Can't render nothing.")

            # Pad the word rows from the end to fit the dimensions
            [row.extend([["-"]] * (width - len(row))) for row in word_grid]
            # Finds the associated image sprite for each word in the input
            # Throws an exception which sends an error message if a word is not found.
            
            # Handles variants based on `:` suffixes
            start = time()
            tile_data = self.bot.get_cog("Admin").tile_data
            try:
                word_grid = self.handle_variants(word_grid, palette=palette)
            except BadTilingVariant as e:
                word, tiling, variant = e.args
                if variant == "":
                    return await ctx.error(f"The name of a variant can't be blank. Make sure there aren't any typos or trailing `:`s in your input around `{word}`.")
                return await ctx.error(f"The tile `{word}` has a tiling type of `{tiling}`, meaning the variant `{variant}` isn't valid for it.")
            except NotFound as e:
                word = e.args[0]
                if (word.startswith("tile_") or word.startswith("text_")) and tile_data.get(word[5:]) is not None:
                    return await ctx.error(f"The tile `{word}` could not be found. Perhaps you meant `{word[5:]}`?")
                if word == "":
                    return await ctx.error("The name of a text tile can't be blank. Make sure there aren't any typos in your input.")
                if tile_data.get("text_" + word) is not None:
                    return await ctx.error(f"The tile `{word}` could not be found. Perhaps you meant `{'text_'+word}`?")
                return await ctx.error(f"The tile `{word}` could not be found or automatically generated.")
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
                if text.startswith("text_") and char == "_":
                    return await ctx.error(f"The text `{text}` could not be generated. Did you mean to generate the text for `{text[5:]}` instead?")
                return await ctx.error(f"The text `{text}` could not be generated, because no appropriate letter sprite exists for `{char}`.")
            except CustomTextTooLong as e:
                text, length = e.args
                return await ctx.error(f"The text `{text}` could not be generated, because it is too long ({length}).")
            except BadLetterStyle as e:
                text = e.args[0]
                return await ctx.error(f"The text `{text}` could not be generated, because the `letter` variant can only be used on text that's two letters long.")
            except BadMetaLevel as e:
                text, depth = e.args
                return await ctx.error(f"The text `{text}` is too meta ({depth} layers). You can only go up to {constants.max_meta_depth} layers deep.")
            except BadPaletteIndex as e:
                text, variant = e.args
                return await ctx.error(f"The text `{text}` could not be generated because the variant `{variant}` is not a valid palette index. The maximum is `4/6`.")

            # Merges the images found
            buffer = BytesIO()
            timestamp = datetime.now()
            format_string = "render_%Y-%m-%d_%H.%M.%S"
            formatted = timestamp.strftime(format_string)
            filename = f"{formatted}.gif"
            task = functools.partial(self.render, word_grid, width, height, palette=palette, background=background, out=buffer, rand=True)
            await self.bot.loop.run_in_executor(None, task)
            delta = time() - start
        # Sends the image through discord
        msg = f"*Rendered in {delta:.2f} s*"
        await ctx.reply(content=msg, file=discord.File(buffer, filename=filename, spoiler=spoiler))
        

    @commands.command()
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
