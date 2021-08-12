from __future__ import annotations
from io import BytesIO

import random
from typing import TYPE_CHECKING, BinaryIO, Literal, overload
import zipfile

import numpy as np
from PIL import Image, ImageChops, ImageFilter

if TYPE_CHECKING:
    from ..tile import FullGrid

from .. import constants, errors
from ..types import Bot
from ..utils import cached_open


class Renderer:
    '''This class exposes various image rendering methods. 
    Some of them require metadata from the bot to function properly.
    '''
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def render(
        self,
        grid: FullGrid,
        *,
        palette: str = "default",
        images: list[str] | None = None,
        image_source: str = "vanilla",
        out: str | BinaryIO = "target/renders/render.gif",
        background: tuple[int, int] | None = None,
        random_animations: bool = False,
        upscale: bool = True,
        extra_out: str | BinaryIO | None = None,
        extra_name: str | None = None,
    ):
        '''Takes a list of tile objects and generates a gif with the associated sprites.

        `out` is a file path or buffer. Renders will be saved there, otherwise to `target/renders/render.gif`.

        `palette` is the name of the color palette to refer to when rendering.

        `images` is a list of background image filenames. Each image is retrieved from `data/images/{image_source}/image`.

        `background` is a palette index. If given, the image background color is set to that color, otherwise transparent. Background images overwrite this. 
        '''
        palette_img = Image.open(f"data/palettes/{palette}.png").convert("RGB")
        sprite_cache = {}
        imgs = []
        # This is appropriate padding, no sprites can go beyond it
        padding = constants.DEFAULT_SPRITE_SIZE
        for frame in range(3):
            width = len(grid[0])
            height = len(grid)
            img_width = width * constants.DEFAULT_SPRITE_SIZE + 2 * padding
            img_height =  height * constants.DEFAULT_SPRITE_SIZE + 2 * padding
            # keeping track of the amount of padding we can slice off
            pad_r=pad_u=pad_l=pad_d=0
            if images and image_source is not None:
                img = Image.new("RGBA", (img_width, img_height))
                # for loop in case multiple background images are used (i.e. baba's world map)
                for image in images:
                    overlap = Image.open(f"data/images/{image_source}/{image}_{frame + 1}.png") # bg images are 1-indexed
                    img.paste(overlap, (padding, padding), mask=overlap)
            # bg color
            elif background is not None:
                palette_color = palette_img.getpixel(background)
                img = Image.new("RGBA", (img_width, img_height), color=palette_color)
            # neither
            else: 
                img = Image.new("RGBA", (img_width, img_height))
            for y, row in enumerate(grid):
                for x, stack in enumerate(row):
                    for tile in stack:
                        if tile.empty:
                            continue
                        wobble = (11 * x + 13 * y + frame) % 3 if random_animations else frame
                        if tile.custom:
                            sprite = self.generate_sprite(
                                tile.name,
                                style=tile.custom_style or "noun",
                                direction=tile.custom_direction,
                                meta_level=tile.meta_level,
                                wobble=wobble,
                            )
                        else:
                            if tile.name in ("icon",):
                                path = f"data/sprites/vanilla/{tile.name}.png"
                            elif tile.name in ("smiley", "hi") or tile.name.startswith("icon"):
                                path = f"data/sprites/vanilla/{tile.name}_1.png"
                            elif tile.name == "default":
                                path = f"data/sprites/vanilla/default_{wobble + 1}.png"
                            else:
                                source, sprite_name = tile.sprite
                                path = f"data/sprites/{source}/{sprite_name}_{tile.variant_number}_{wobble + 1}.png"
                            sprite = cached_open(path, cache=sprite_cache, fn=Image.open).convert("RGBA")
                            
                            sprite = await self.apply_options_name(
                                tile.name,
                                sprite,
                                style=tile.custom_style or "noun",
                                direction=tile.custom_direction,
                                meta_level=tile.meta_level,
                                wobble=wobble,
                            )
                        # Color conversion
                        r, g, b = tile.color_rgb if tile.color_rgb is not None else palette_img.getpixel(tile.color_index)
                        arr = np.asarray(sprite, dtype='float64')
                        arr[..., 0] *= r / 256
                        arr[..., 1] *= g / 256
                        arr[..., 2] *= b / 256
                        sprite = Image.fromarray(arr.astype('uint8'))
                        x_offset = (sprite.width - constants.DEFAULT_SPRITE_SIZE) // 2
                        y_offset = (sprite.height - constants.DEFAULT_SPRITE_SIZE) // 2
                        if x == 0:
                            pad_l = max(pad_l, x_offset)
                        if x == width - 1:
                            pad_r = max(pad_r, x_offset)
                        if y == 0:
                            pad_u = max(pad_u, y_offset)
                        if y == height - 1:
                            pad_d = max(pad_d, y_offset)
                        img.paste(sprite, (x * constants.DEFAULT_SPRITE_SIZE + padding - x_offset, y * constants.DEFAULT_SPRITE_SIZE + padding - y_offset), mask=sprite)
            
            img = img.crop((padding - pad_l, padding - pad_u, img.width - padding + pad_r, img.height - padding + pad_d))
            if upscale:
                img = img.resize((2 * img.width, 2 * img.height), resample=Image.NEAREST)
            imgs.append(img)

        self.save_frames(
            imgs,
            out,
            extra_out=extra_out,
            extra_name=extra_name
        )

    def generate_sprite(
        self,
        text: str,
        *,
        style: str,
        direction: int | None,
        meta_level: int,
        wobble: int,
        seed: int | None = None
    ) -> Image.Image:
        '''Generates a custom text sprite'''
        text = text[5:]
        raw = text.replace("/", "")
        newline_count = text.count("/")

        # This is to prevent possible DOS attacks using massive text
        # Note however that this is unlikely to be an issue unless this
        # function takes input from unexpected sources, as even 8 ** 4000
        # is relatively okay to compute
        # The default is low enough to prevent abuse, but high enough to 
        # ensure that no actual text can be excluded.
        if len(raw) > constants.MAX_TEXT_LENGTH:
            raise errors.CustomTextTooLong(text)

        if seed is None:
            seed = random.randint(0, 8 ** len(raw))
        
        # Get mode and split status
        if newline_count > 1:
            raise errors.TooManyLines(text, newline_count)
        elif newline_count == 1:
            fixed = True
            mode = "small"
            index = text.index("/")
        else:
            fixed = False
            mode = "big"
            index = -1
            if len(raw) >= 4:
                mode = "small"
                index = len(raw) - len(raw) // 2
    
        if style == "letter":
            if mode == "big":
                mode = "letter"
            else:
                raise errors.BadLetterStyle(text)
        
        if index == 0 or index == len(raw):
            raise errors.LeadingTrailingLineBreaks(text)

        # fetch the minimum possible widths first
        try:
            widths: list[int] = [self.bot.db.letter_width(c, mode, greater_than=0) for c in raw]
        except KeyError as e:
            raise errors.BadCharacter(text, mode, e.args[0])

        max_width = constants.DEFAULT_SPRITE_SIZE
        def check_or_adjust(widths: list[int], index: int) -> int:
            '''Is the arrangement valid?'''
            if mode == "small":
                if fixed:
                    if sum(widths[:index]) > max_width or sum(widths[index:]) > max_width:
                        raise errors.CustomTextTooLong(text)
                else:
                    if sum(widths) > 2 * max_width:
                        raise errors.CustomTextTooLong(text)
                    while sum(widths[:index]) > max_width:
                        index -= 1
                    while sum(widths[index:]) > max_width:
                        index += 1
                    if sum(widths[:index]) > max_width or sum(widths[index:]) > max_width:
                        raise errors.CustomTextTooLong(text)
                    if index == 0 or index == len(raw):
                        raise errors.CustomTextTooLong(text)
                    return index
            else:
                if sum(widths) > max_width:
                    raise errors.CustomTextTooLong(text)
            return index
        
        def too_squished(widths: list[int], index: int) -> bool:
            '''Is the arrangement too squished? (bad letter spacing)'''
            if mode == "small":
                top = widths[:index]
                top_gaps = max_width - sum(top)
                bottom = widths[index:]
                bottom_gaps = max_width - sum(bottom)
                return top_gaps < len(top) - 1 or bottom_gaps < len(bottom) - 1
            else:
                gaps = max_width - sum(widths)
                return gaps < len(widths) - 1
        
        # Check if the arrangement is valid with minimum sizes
        # If allowed, shift the index to make the arrangement valid
        index = check_or_adjust(widths, index)

        # Wxpand widths where possible
        stable = [False for _ in range(len(widths))]
        while not all(stable):
            old_width, i = min((w, i) for i, w in enumerate(widths) if not stable[i])
            try:
                new_width = self.bot.db.letter_width(raw[i], mode, greater_than=old_width)
            except KeyError:
                stable[i] = True
                continue
            widths[i] = new_width
            try:
                index = check_or_adjust(widths, index)
            except errors.CustomTextTooLong:
                widths[i] = old_width
                stable[i] = True
            else:
                if too_squished(widths, index):
                    # We've shown that a "perfect" width already exists below this
                    # So stick to the "perfect" one
                    widths[i] = old_width
                    stable[i] = True

        # Arrangement is now the widest it can be
        # Kerning: try for 1 pixel between sprites, and rest to the edges
        gaps: list[int] = []
        if mode == "small":
            rows = [widths[:index], widths[index:]]
        else:
            rows = [widths[:]]
        for row in rows:
            space = max_width - sum(row)
            # Extra -1 is here to not give kerning space outside the left/rightmost char
            chars = len(row) - 1
            if space >= chars:
                # left edge
                gaps.append((space - chars) // 2)
                # char gap
                gaps.extend([1] * chars)
                # right edge gap is implied
            else:
                # left edge
                gaps.append(0)
                # as many char gaps as possible, starting from the left
                gaps.extend([1] * space)
                gaps.extend([0] * (chars - space))

        letters: list[Image.Image] = []
        for c, w in zip(raw, widths):
            letters.append(self.bot.db.letter_sprite(c, mode, w, wobble, seed=seed | 0b11111111))
            seed >>= 8
        
        sprite = Image.new("L", (constants.DEFAULT_SPRITE_SIZE, constants.DEFAULT_SPRITE_SIZE))
        if mode == "small":
            x = gaps[0]
            y_center = 6
            for i in range(index):
                letter = letters[i]
                y_top = y_center - letter.height // 2
                sprite.paste(letter, (x, y_top), mask=letter)
                x += widths[i]
                if i != index - 1:
                    x += gaps[i + 1]
            x = gaps[index]
            y_center = 18
            for i in range(index, len(raw)):
                letter = letters[i]
                y_top = y_center - letter.height // 2
                sprite.paste(letter, (x, y_top), mask=letter)
                x += widths[i]
                if i != len(raw) - 1:
                    x += gaps[i + 1]
        else:
            x = gaps[0]
            y_center = 12
            for i in range(len(raw)):
                letter = letters[i]
                y_top = y_center - letter.height // 2
                sprite.paste(letter, (x, y_top), mask=letter)
                x += widths[i]
                if i != len(raw) - 1:
                    x += gaps[i + 1]
            
        sprite = Image.merge("RGBA", (sprite, sprite, sprite, sprite))
        return self.apply_options(
            sprite, 
            original_style="noun",
            style=style,
            original_direction=None,
            direction=direction,
            meta_level=meta_level,
            wobble=wobble
        )

    async def apply_options_name(
        self,
        name: str,
        sprite: Image.Image,
        *,
        style: str,
        direction: int | None,
        meta_level: int,
        wobble: int
    ) -> Image.Image:
        '''Takes an image, taking tile data from its name, and applies the given options to it.'''
        tile_data = await self.bot.db.tile(name)
        assert tile_data is not None
        original_style = constants.TEXT_STYLES[tile_data.get("type", "0")]
        original_direction = tile_data.get("text_direction")
        try:
            return self.apply_options(
                sprite,
                original_style=original_style,
                style=style,
                original_direction=original_direction,
                direction=direction,
                meta_level=meta_level,
                wobble=wobble,
            )
        except ValueError as e:
            size = e.args[0]
            raise errors.BadTileProperty(name, size)

    def apply_options(
        self,
        sprite: Image.Image,
        *, 
        original_style: str,
        style: str,
        original_direction: int | None,
        direction: int | None,
        meta_level: int,
        wobble: int
    ):
        '''Takes an image, with or without a plate, and applies the given options to it.'''
        if meta_level != 0 or style != "noun" and (original_style != style or original_direction != direction):
            if original_style == "property":
                # box: position of upper-left coordinate of "inner text" in the larger text tile
                plate, box = self.bot.get.plate(original_direction, wobble)
                plate_alpha = ImageChops.invert(plate.getchannel("A"))
                sprite_alpha = ImageChops.invert(sprite.getchannel("A"))
                alpha = ImageChops.subtract(sprite_alpha, plate_alpha)
                sprite = Image.merge("RGBA", (alpha, alpha, alpha, alpha))
                sprite = sprite.crop((box[0], box[1], constants.DEFAULT_SPRITE_SIZE + box[0], constants.DEFAULT_SPRITE_SIZE + box[1]))
            if style == "property":
                if sprite.height != constants.DEFAULT_SPRITE_SIZE or sprite.width != constants.DEFAULT_SPRITE_SIZE:
                    raise ValueError(sprite.size)
                plate, box = self.bot.get.plate(direction, wobble)
                plate = self.make_meta(plate, meta_level)
                plate_alpha = plate.getchannel("A")
                sprite_alpha = sprite.getchannel("A").crop(
                    (-meta_level, -meta_level, sprite.width + meta_level, sprite.height + meta_level)
                ).crop(
                    (-box[0], -box[0], constants.DEFAULT_SPRITE_SIZE + box[0], constants.DEFAULT_SPRITE_SIZE + box[1])
                )
                if meta_level % 2 == 0:
                    alpha = ImageChops.subtract(plate_alpha, sprite_alpha)
                else:
                    alpha = ImageChops.add(plate_alpha, sprite_alpha)
                sprite = Image.merge("RGBA", (alpha, alpha, alpha, alpha))
            else:
                sprite = self.make_meta(sprite, meta_level)
        return sprite

    def make_meta(self, img: Image.Image, level: int) -> Image.Image:
        '''Applies a meta filter to an image.'''
        if level > constants.MAX_META_DEPTH:
            raise ValueError(level)
        
        orig = img.copy()
        base = img.getchannel("A")
        for _ in range(level):
            temp = base.crop((-2, -2, base.width + 2, base.height + 2))
            filtered = ImageChops.invert(temp).filter(ImageFilter.FIND_EDGES)
            base = filtered.crop((1, 1, filtered.width - 1, filtered.height - 1))
        
        base = Image.merge("RGBA", (base, base, base, base))
        if level % 2 == 0 and level != 0:
            base.paste(orig, (level, level), mask=orig)
        
        return base

    def save_frames(
        self,
        imgs: list[Image.Image],
        out: str | BinaryIO,
        extra_out: str | BinaryIO | None = None,
        extra_name: str | None = None
    ) -> None:
        '''Saves the images as a gif to the given file or buffer.
        
        If a buffer, this also conveniently seeks to the start of the buffer.

        If extra_out is provided, the frames are also saved as a zip file there.
        '''
        imgs[0].save(
            out, 
            format="GIF",
            save_all=True,
            append_images=imgs[1:],
            loop=0,
            duration=200,
            disposal=2, # Frames don't overlap
            transparency=255,
            background=255,
            optimize=False # Important in order to keep the color palettes from being unpredictable
        )
        if not isinstance(out, str):
            out.seek(0)
        if extra_name is not None and extra_out is not None:
            file = zipfile.PyZipFile(extra_out, "x")
            for i, img in enumerate(imgs):
                buffer = BytesIO()
                img.save(buffer, "PNG")
                file.writestr(f"{extra_name}_{i+1}.png", buffer.getvalue())
            file.close()

def setup(bot: Bot):
    bot.renderer = Renderer(bot)
