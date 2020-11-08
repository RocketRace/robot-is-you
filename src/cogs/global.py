import discord
import random
import re
import zipfile

from datetime    import datetime
from discord.ext import commands
from functools   import partial
from inspect     import Parameter
from io          import BytesIO
from json        import load
from os          import listdir
from os.path     import isfile
from PIL         import Image, ImageChops, ImageFilter, ImageDraw, ImageOps
from string      import ascii_lowercase
from src.utils   import *
from time        import time

valid_colors = {
    "red":(2, 2),
    "orange":(2, 3),
    "yellow":(2, 4),
    "lime":(5, 3),
    "green":(5, 2),
    "cyan":(1, 4),
    "blue":(1, 3),
    "purple":(3, 1),
    "pink":(4, 1),
    "rosy":(4, 2),
    "grey":(0, 1),
    "black":(0, 4),
    "silver":(0, 2),
    "white":(0, 3),
    "brown":(6, 1),
}

def flatten(items, seqtypes=(list, tuple)):
    '''Flattens nested iterables, of speficied types.
    Via https://stackoverflow.com/a/10824086
    '''
    for i, _ in enumerate(items):
        while i < len(items) and isinstance(items[i], seqtypes):
            items[i:i+1] = items[i]
    return items

def try_index(string, value):
    '''Returns the index of a substring within a string.
    Returns -1 if not found.
    '''
    index = -1
    try:
        index = string.index(value)
    except:
        pass
    return index

class SplittingException(BaseException):
    pass

# Splits the "text_x,y,z..." shortcuts into "text_x", "text_y", ...
def split_commas(grid, prefix):
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
    def __init__(self, bot):
        self.bot = bot
        with open("config/leveltileoverride.json") as f:
            j = load(f)
            self.level_tile_override = j

    # Check if the bot is loading
    async def cog_check(self, ctx):
        '''Only if the bot is not loading assets'''
        return not self.bot.loading

    def save_frames(self, frames, fp):
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

    def make_meta(self, name, img, meta_level):
        if meta_level > 3:
            raise ValueError(name, meta_level, "meta")
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
            ImageDraw.floodfill(base, (0, 0), 0)
            base = base.crop((2, 2, base.width - 2, base.height - 2))
            base = base.convert("1")
            final = base.convert("RGBA")
            final.putalpha(base)
        if meta_level >= 2 and meta_level % 2 == 0:
            final.paste(original, (i + 1, i + 1), original.convert("L"))
        elif meta_level >= 2 and meta_level % 2 == 1:
            final.paste(ImageChops.invert(original), (i + 1, i + 1), original.convert("L"))
        
        return final
        

    def magick_images(self, word_grid, width, height, *, palette="default", images=None, image_source="vanilla", out="target/renders/render.gif", background=None, rand=False):
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
                        if tile.name in ("icon", "plus"):
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
                            tile.color = self.bot.get_cog("Admin").tile_data.get(tile.name).get("active")
                            if tile.color is None:
                                tile.color = self.bot.get_cog("Admin").tile_data.get(tile.name).get("color")
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
                palette_img = Image.open(f"data/palettes/{palette}.png").convert("RGBA") # ensure alpha channel exists, even if blank
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

    def handle_variants(self, grid, *, tile_borders=False, is_level=False, palette="default"):
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
        
        colors = {
            "red":(2, 2),
            "orange":(2, 3),
            "yellow":(2, 4),
            "lime":(5, 3),
            "green":(5, 2),
            "cyan":(1, 4),
            "blue":(1, 3),
            "purple":(3, 1),
            "pink":(4, 1),
            "rosy":(4, 2),
            "grey":(0, 1),
            "black":(0, 4),
            "silver":(0, 2),
            "white":(0, 3),
            "brown":(6, 1),
        }

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
                            if colors.get(variant) is not None:
                                final.color = colors.get(variant)
                                delete.append(i)
                            elif ',' in variant:
                                try:
                                    final.color = tuple(map(int, variant.split(',')))
                                    delete.append(i)
                                except:
                                    raise FileNotFoundError(word)
                            elif variant == "inactive":
                                # If an active variant exists, the default color is inactive
                                if tile_data and tile_data.get("active"):
                                    final.color = tuple(map(int, tile_data["color"]))
                                    delete.append(i)
                                else:
                                    raise FileNotFoundError(word)
                            # META SPRITES
                            elif variant == "meta":
                                final.meta_level += 1
                                delete.append(i)
                        delete.reverse()
                        for i in delete:
                            variants.pop(i)
                        # Force custom-rendered text
                        # This has to be rendered beforehand (each sprite can't be generated separately)
                        # because generated sprites uses randomly picked letters
                        if tile_data is None or "property" in variants or "noun" in variants or "letter" in variants:
                            if tile.startswith("text_"):
                                final.custom = True
                                if "property" in variants:
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
                            raise FileNotFoundError(tile)

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

                        # Apply actual sprite variants
                        for variant in variants:
                            # SPRITE VARIANTS
                            # TODO: clean this up big time
                            if tiling == "-1":
                                if variant in ("r", "right"):
                                    direction = 0
                                elif variant == "0":
                                    final.variant = variant
                                else: 
                                    if is_level:
                                        direction = 0
                                    else:
                                        raise FileNotFoundError(word)
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
                                else:
                                    if is_level:
                                        direction = 0
                                    else:
                                        raise FileNotFoundError(word)
                            elif tiling == "1":
                                if is_level:
                                    direction = 0
                                else:
                                    raise FileNotFoundError(word)
                            elif tiling == "2":
                                if variant in ("r", "right"):
                                    direction = 0
                                elif variant in ("u", "up"):
                                    direction = 1
                                elif variant in ("l", "left"):
                                    direction = 2
                                elif variant in ("d", "down"):
                                    direction = 3
                                elif variant in ("s", "sleep"): 
                                    animation_frame = -1
                                elif variant in (
                                    "31", "0", "1", "2", "3", 
                                    "7", "8", "9", "10", "11",
                                    "15", "16", "17", "18", "19",
                                    "23", "24", "25", "26", "27",
                                ): 
                                    final.variant = variant
                                else:
                                    if is_level:
                                        direction = 0
                                    else:
                                        raise FileNotFoundError(word)
                            elif tiling == "3":
                                if variant in ("r", "right"):
                                    direction = 0
                                elif variant in ("u", "up"):
                                    direction = 1
                                elif variant in ("l", "left"):
                                    direction = 2
                                elif variant in ("d", "down"):
                                    direction = 3
                                elif variant in (
                                    "0", "1", "2", "3", 
                                    "8", "9", "10", "11",
                                    "16", "17", "18", "19",
                                    "24", "25", "26", "27",
                                ): 
                                    final.variant = variant
                                else:
                                    if is_level:
                                        direction = 0
                                    else:
                                        raise FileNotFoundError(word)
                            elif tiling == "4":
                                if variant in ("r", "right"):
                                    direction = 0
                                elif variant in (
                                    "0", "1", "2", "3", 
                                ):
                                    final.variant = variant
                                else:
                                    if is_level:
                                        direction = 0
                                    else:
                                        raise FileNotFoundError(word)

                        # Compute the final variant, if not already set
                        if tiling != "1":
                            final.variant = str(final.variant or (8 * direction + animation_frame) % 32)

                        # Finally, push the sprite to the grid
                        grid[y][x][z] = final
        return grid

    @commands.group(invoke_without_command=True)
    @commands.cooldown(2, 10, commands.BucketType.channel)
    async def make(self, ctx, text, color = None, style = "noun", meta_level = "0", palette = "default"):
        '''Generates a custom text sprite. 
        Use "/" in the text to force a line break.

        The `color` argument can be a hex color (`"#ffffff"`) or a string (`"red"`).

        The `style` argument may be "noun", "property", or "letter".
        
        The `meta_level` argument may be "0", "1", "2" or "3".

        The `palette` argument can be set to the name of a palette.
        '''
        # These colors are based on the default palette
        if color is not None:
            real_color = color.lower()
            if real_color.startswith("#"): 
                int_color = int(real_color[1:], base=16) & (2 ** 24 - 1)
                byte_color = (int_color >> 16, (int_color & 255 << 8) >> 8, int_color & 255)
                tile_color = (byte_color[0] / 256, byte_color[1] / 256, byte_color[2] / 256)
            elif real_color.startswith("0x"):
                int_color = int(real_color, base=16)
                byte_color = (int_color >> 16, (int_color & 255 << 8) >> 8, int_color & 255)
                tile_color = (byte_color[0] / 256, byte_color[1] / 256, byte_color[2] / 256)
            elif real_color in valid_colors:
                try:
                    palette_img = Image.open(f"data/palettes/{palette}.png").convert("RGB")
                    color_index = valid_colors[real_color]
                    tile_color = tuple(p/256 for p in palette_img.getpixel(color_index))
                except FileNotFoundError:
                    return await self.bot.error(ctx, f"The palette `{palette}` is not valid.")
            else:
                return await self.bot.error(ctx, f"The color `{color}` is invalid.")
        else:
            tile_color = (1, 1, 1)
        if style not in ("noun", "property", "letter"):
            return await self.bot.error(ctx, f"The style `{style}` is not valid.")
        try:
            meta_level = int(meta_level)
            buffer = BytesIO()
            tile = Tile(name=text.lower(), color=tile_color, style=style.lower(), custom=True)
            tile.images = self.generate_tile(tile.name, color=tile.color, style=style, meta_level=meta_level)
            self.magick_images([[[tile]]], 1, 1, out=buffer)
            await ctx.send(ctx.author.mention, file=discord.File(buffer, filename=f"custom_'{text.replace('/','')}'.gif"))
        except ValueError as e:
            text = e.args[0]
            culprit = e.args[1]
            reason = e.args[2]
            if reason == "variant":
                return await self.bot.error(ctx, f"The text `{text}` could not be generated, because the variant `{culprit}` is invalid.")
            if reason == "width":
                if len(text) < 20:
                    return await self.bot.error(ctx, f"The text `{text}` could not be generated, because it is too long.")
                return await self.bot.error(ctx, f"The text `{text[:20]}` could not be generated, because it is too long.")
            if reason == "char":
                return await self.bot.error(ctx, f"The text `{text}` could not be generated, because no letter sprite exists for `{culprit}`.")
            if reason == "zero":
                return await self.bot.error(ctx, f"The input cannot be empty.")
            if reason == "letter":
                return await self.bot.error(ctx, "You can only apply the letter style for 1 or 2 letter words.")
            return await self.bot.error(ctx, f"The text `{text}` could not be generated.")
        
    @make.command()
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def raw(self, ctx, text, style="noun", meta_level = "0"):
        '''Returns a zip archive of the custom tile.

        A raw sprite has no color!

        The `style` argument may be "noun", "property", or "letter".
        
        The `meta_level` argument may be "0", "1", "2" or "3".
        '''
        real_text = text.lower()
        if style not in ("noun", "property", "letter"):
            return await self.bot.error(ctx, f"`{style}` is not a valid style. It must be one of `noun`, `property` or `letter`.")
        if meta_level not in "0123":
            return await self.bot.error(ctx, f"`{meta_level}` is not a valid meta level. It must be one of `0`, `1`, `2` or `3`.")
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
            await ctx.send(
                f"{ctx.author.mention} *Raw sprites for `text_{meta_level*'meta_'}{real_text.replace('/','')}`*", 
                file = discord.File(buffer, filename=f"custom_{meta_level*'meta_'}{real_text.replace('/','')}_sprites.zip")
            )
        except ValueError as e:
            text = e.args[0]
            culprit = e.args[1]
            reason = e.args[2]
            if reason == "variant":
                return await self.bot.error(ctx, f"The text `{text}` could not be generated, because the variant `{culprit}` is invalid.")
            if reason == "width":
                return await self.bot.error(ctx, f"The text `{text[:20]}` could not be generated, because it is too long.")
            if reason == "char":
                return await self.bot.error(ctx, f"The text `{text}` could not be generated, because no letter sprite exists for `{culprit}`.")
            if reason == "zero":
                return await self.bot.error(ctx, f"The input cannot be empty.")
            if reason == "letter":
                return await self.bot.error(ctx, "You can only apply the letter style for 1 or 2 letter words.")
            return await self.bot.error(ctx, f"The text `{text}` could not be generated.")

    def generate_tile(self, text, color, style, meta_level, seed=None):
        '''
        Custom tile => rendered custom tile
        '''
        if seed is not None:
            random.seed(seed)
        clean = text.replace("/", "")
        forced = len(clean) != len(text)
        size = len(clean)
        if text.count("/") >= 2:
            raise ValueError(text, None, "slash")
        elif text.count("/") == 1 and size == 1:
            raise ValueError(text, None, "slash")

        if size == 0:
            raise ValueError(text, None, "zero")
        if size == 1:
            if text.isascii() and (text.isalnum() or text == "*"):
                paths = [
                    f"data/sprites/{'vanilla' if text.isalnum() else 'misc'}/text_{text}_0"
                ]
                positions = [
                    (12, 12)
                ]
            else:
                raise ValueError(text, text, "char")
        elif size == 2 and style == "letter":
            if text.isascii() and all(k.isalnum() or k == "*" for k in text):
                paths = [
                    f"target/letters/thick/text_{text[0]}_0",
                    f"target/letters/thick/text_{text[1]}_0",
                ]
                positions = [
                    (6, 12),
                    (18, 12)
                ]
            else:
                raise ValueError(text, text, "char")
        elif size > 10:
            raise ValueError(text, None, "width")
        elif style == "letter":
            raise ValueError(text, None, "letter")
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
                    if 0 in split:
                        raise ValueError(text, None, "slash")
                else:
                    # Prefer more on the top
                    split = [(size + 1) // 2, size // 2]
                arrangement = [24 // split[0]] * split[0] + [24 // split[1]] * split[1]
                positions = [(int(24 // split[0] * (pos + 0.5)), 6) for pos in range(split[0])] + \
                    [(int(24 // split[1] * (pos + 0.5)), 18) for pos in range(split[1])]
            try:
                widths = {x: data[x] for x in clean}
            except KeyError as e:
                raise ValueError(text, e.args[0], "char")

            
            final_arrangement = []
            for char, limit in zip(clean, arrangement):
                top = 0
                second = 0
                for width in widths[char]:
                    if top <= width <= limit:
                        second = top
                        top = width
                if top == 0:
                    raise ValueError(text, char, "width")
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
            base = Image.new("1", (24, 24), color=0)
            if style == "property":
                plate = Image.open(f"data/sprites/vanilla-extensions/plate_0_{frame+1}.png").convert("1")
                base = ImageChops.invert(ImageChops.add(base, plate))
            
            for (x, y), sprite in zip(positions, letter_sprites):
                s_x, s_y = sprite.size
                base.paste(sprite, box=(x - s_x // 2, y - s_y // 2), mask=sprite)

            if style == "property":
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

    async def render_tiles(self, ctx, *, objects, rule):
        '''Performs the bulk work for both `tile` and `rule` commands.'''
        async with ctx.typing():
            render_limit = 100
            tiles = objects.lower().strip().replace("\\", "")
            if tiles == "":
                param = Parameter("objects", Parameter.KEYWORD_ONLY)
                raise commands.MissingRequiredArgument(param)

            # Determines if this should be a spoiler
            spoiler = "|" in tiles
            tiles = tiles.replace("|", "")
            
            # Check for empty input
            if not tiles:
                return await self.bot.error(ctx, "Input cannot be blank.")

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
                if re.fullmatch(r"--background|-b|background:true", flag):
                    background = (0, 4)
                    to_delete.append((x, y))
                    continue
                flag_match = re.fullmatch(r"(--palette=|-p=|palette:)(\w+)", flag)
                if flag_match:
                    palette = flag_match.group(2)
                    if palette + ".png" not in listdir("data/palettes"):
                        return await self.bot.error(ctx, f"Could not find a palette with name \"{palette}\".")
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
                return await self.bot.error(ctx, f"I couldn't parse the following input: \"{source_of_exception}\".")

            # Splits "&"-joined words into stacks
            for row in word_grid:
                for i,stack in enumerate(row):
                    if "&" in stack:
                        row[i] = stack.split("&")
                    else:
                        row[i] = [stack]
                    # Limit how many tiles can be rendered in one space
                    height = len(row[i])
                    if height > 3 and ctx.author.id != self.bot.owner_id:
                        return await self.bot.error(ctx, f"Stack too high ({height}).", "You may only stack up to 3 tiles on one space.")

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
            if area > render_limit and ctx.author.id != self.bot.owner_id:
                return await self.bot.error(ctx, f"Too many tiles ({area}).", f"You may only render up to {render_limit} tiles at once, including empty tiles.")
            elif area == 0:
                return await self.bot.error(ctx, f"Can't render nothing.")

            # Pad the word rows from the end to fit the dimensions
            [row.extend([["-"]] * (width - len(row))) for row in word_grid]
            # Finds the associated image sprite for each word in the input
            # Throws an exception which sends an error message if a word is not found.
            
            # Handles variants based on `:` suffixes
            start = time()
            try:
                word_grid = self.handle_variants(word_grid, palette=palette)
            except (ValueError, FileNotFoundError) as e:
                if isinstance(e, FileNotFoundError):
                    tile_data = self.bot.get_cog("Admin").tile_data
                    tile = e.args[0]
                    variants = None
                    if ":" in tile:
                        variants = ":" + ":".join(tile.split(":")[1:])
                        tile = tile.split(":")[0]
                    # Error cases
                    if tile_data.get(tile) is not None:
                        if variants is None:
                            return await self.bot.error(ctx, f"The tile `{tile}` exists but a sprite could not be found for it.")
                        return await self.bot.error(ctx, f"The tile `{tile}` exists but the sprite variant(s) `{variants}` are not valid for it.")
                    if tile_data.get("text_" + tile) is not None:
                        if not rule:
                            return await self.bot.error(ctx, f"The tile `{tile}` does not exist, but the tile `text_{tile}` does.", "You can also use the `rule` command instead of the `tile command.")
                        return await self.bot.error(ctx, f"The tile `{tile}` does not exist, but the tile `text_{tile}` does.")
                    if tile.startswith("text_") and tile_data.get(tile[5:]) is not None:
                        if rule:
                            return await self.bot.error(ctx, f"The tile `{tile}` does not exist, but the tile `{tile[5:]}` does.", "Did you mean to type `tile_{tile}`.")
                        return await self.bot.error(ctx, f"The tile `{tile}` does not exist, but the tile `{tile[5:]}` does.")
                    return await self.bot.error(ctx, f"The tile `{tile}` does not exist.")
                tile = e.args[0]
                culprit = e.args[1]
                reason = e.args[2]
                if reason == "variant":
                    return await self.bot.error(ctx, f"The tile `{tile}` could not be automatically generated, because the variant `{culprit}` is invalid.")
                if reason == "width":
                    return await self.bot.error(ctx, f"The tile `{tile[:20]}` could not be automatically generated, because it is too long.")
                if reason == "char":
                    return await self.bot.error(ctx, f"The tile `{tile}` could not be automatically generated, because no letter sprite exists for `{culprit}`.")
                if reason == "zero":
                    return await self.bot.error(ctx, f"Cannot apply variants to an empty tile.")
                if reason == "meta":
                    return await self.bot.error(ctx, "You can only go three layers of meta deep.")
                if reason == "letter":
                    return await self.bot.error(ctx, "You can only apply the letter style for 1 or 2 letter words.")
                return await self.bot.error(ctx, f"The tile `{tile}` was not found, and could not be automatically generated.")

            # Merges the images found
            buffer = BytesIO()
            timestamp = datetime.now()
            format_string = "render_%Y-%m-%d_%H.%M.%S"
            formatted = timestamp.strftime(format_string)
            filename = f"{formatted}.gif"
            task = partial(self.magick_images, word_grid, width, height, palette=palette, background=background, out=buffer, rand=True)
            try:
                await self.bot.loop.run_in_executor(None, task)
            except ValueError:
                return await self.bot.error(ctx, f"You can only apply apply three layers of meta.")
            delta = time() - start
        # Sends the image through discord
        msg = f"{ctx.author.mention}\n*Rendered in {delta:.2f} s*"
        await ctx.send(content=msg, file=discord.File(buffer, filename=filename, spoiler=spoiler))
        

    @commands.command()
    @commands.cooldown(5, 10, type=commands.BucketType.channel)
    async def rule(self, ctx, *, objects = ""):
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
    @commands.cooldown(5, 10, type=commands.BucketType.channel)
    async def tile(self, ctx, *, objects = ""):
        '''Renders the tiles provided.

       **Flags**
        * `--palette=<...>` (`-P=<...>`): Recolors the output gif. See the `palettes` command for more.
        * `--background` (`-B`): Enables background color.
        
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

    @commands.cooldown(5, 10, commands.BucketType.channel)
    @commands.command(name="level")
    async def _level(self, ctx, *, query):
        '''Renders the given Baba Is You level.

        Levels are searched for in the following order:
        * Checks if the input matches the level ID (e.g. "20level")
        * Checks if the input matches the level number (e.g. "space-3" or "lake-extra 1")
        * Checks if the input matches the level name (e.g. "further fields")
        * Checks if the input is the ID of a world (e.g. "cavern")
        '''
        # User feedback
        await ctx.trigger_typing()

        levels = {}
        # Lower case, make the query all nice
        fine_query = query.lower().strip()
        # Is it the level ID?
        level_data = self.bot.get_cog("Reader").level_data
        if level_data.get(fine_query) is not None:
            levels[fine_query] = level_data[fine_query]

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
                    style = "0"
                    number = identifier
                elif len(identifier) == 1 and identifier.isalpha():
                    # Letters (only 1 letter)
                    style = "1"
                    # 0 <--> a
                    # 1 <--> b
                    # ...
                    # 25 <--> z
                    raw_number = try_index(ascii_lowercase, identifier)
                    # If the identifier is a lowercase letter, set "number"
                    if raw_number != -1: number = str(raw_number)
                elif identifier.startswith("extra") and identifier[5:].strip().isnumeric():
                    # Extra numbers:
                    # Starting with "extra", ending with numbers
                    style = "2"
                    number = str(int(identifier[5:].strip()) - 1)
                else:
                    number = identifier
                    style = "-1"
                if style is not None and number is not None:
                    # Custom map ID?
                    if style == "-1":
                        # Check for the map ID & custom identifier combination
                        for filename,data in level_data.items():
                            if data["mapID"] == number and data["parent"] == map_id:
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
                if data["mapID"] == query and data["parent"] is None:
                    levels[filename] = data

        # If not found: error message
        if len(levels) == 0:
            return await self.bot.error(ctx, f'Could not find a level matching the query "{fine_query}".')

        # If found:
        else:
            # Is there more than 1 match?
            matches = len(levels)

            # The first match
            data = list(levels.items())
            level_id = data[0][0]
            level = data[0][1]

            # The embedded file
            gif = discord.File(f"target/renders/{level['source']}/{level_id}.gif", spoiler=True)
            
            # Level name
            name = level["name"]

            # Level parent 
            parent = level.get("parent")
            map_id = level.get("mapID")
            tree = ""
            # Parse the display name
            if parent is not None:
                # With a custom mapID
                if map_id is not None:
                    # Format
                    tree = parent + "-" + map_id + ": "
                else:
                    # Parse the level style
                    style = level["style"]
                    number = level["number"]
                    identifier = None
                    # Regular numbers
                    if style == "0":
                        identifier = number
                    elif style == "1":
                    # Letters
                        identifier = ascii_lowercase[int(number)]
                    elif style == "2":
                    # Extra dots
                        identifier = "extra " + str(int(number) + 1)
                    else: 
                    # In case the custom map ID wasn't already set
                        identifier = map_id
                    # format
                    tree = parent + "-" + identifier + ": "
            
            # Level subtitle, if any
            subtitle = ""
            if level.get("subtitle") is not None:
                subtitle = "\nSubtitle: `" + level["subtitle"] + "`"

            # Any additional matches
            matches_text = "" if matches == 1 else f"\nFound {matches} matches: `{', '.join([l for l in levels])}`, showing the first." 

            # Formatted output
            formatted = f"{ctx.author.mention}{matches_text}\nName: `{tree}{name}`\nID: `{level_id}`{subtitle}"

            # Only the author should be mentioned
            mentions = discord.AllowedMentions(everyone=False, users=[ctx.author], roles=False)

            # Send the result
            await ctx.send(formatted, file=gif, allowed_mentions=mentions)

def setup(bot):
    bot.add_cog(GlobalCog(bot))
