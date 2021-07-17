from __future__ import annotations

import random
from typing import TYPE_CHECKING, BinaryIO, Literal

import numpy as np
from PIL import Image, ImageChops, ImageFilter

if TYPE_CHECKING:
    from ..tile import FullGrid

from .. import constants
from ..types import Bot
from ..utils import cached_open


class Renderer:
    '''This class exposes various image rendering methods. 
    Some of them require metadata from the bot to function properly.
    '''
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    def render(
        self,
        grid: FullGrid,
        *,
        palette: str = "default",
        images: list[Image.Image] | None = None,
        image_source: str = "vanilla",
        out: str | BinaryIO = "target/renders/render.gif",
        background: tuple[int, int] | None = None,
        random_animations: bool = False,
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
            if images is not None and image_source is not None:
                img = Image.new("RGBA", (img_width, img_height))
                # for loop in case multiple background images are used (i.e. baba's world map)
                for image in images:
                    overlap = Image.open(f"data/images/{image_source}/{image}_{frame + 1}.png") # bg images are 1-indexed
                    mask = overlap.getchannel("A")
                    img.paste(overlap, mask=mask)
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
                                style=tile.custom_style, # type: ignore
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
                            
                            sprite = self.apply_options(
                                tile.name,
                                sprite,
                                style=tile.custom_style, # type: ignore
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
            img = img.resize((2 * img.width, 2 * img.height), resample=Image.NEAREST)
            imgs.append(img)

        self.save_frames(imgs, out)

    def generate_sprite(
        self,
        text: str,
        *,
        style: Literal["noun", "property", "letter"],
        direction: int | None,
        meta_level: int,
        wobble: int
    ) -> Image.Image:
        '''Do the thing'''

    def apply_options(
        self,
        name: str,
        sprite: Image.Image,
        *,
        style: Literal["noun", "property", "letter"] | None,
        direction: int | None,
        meta_level: int,
        wobble: int
    ) -> Image.Image:
        '''Takes an image, with or without a plate, and applies the given options to it.'''
        tile_data = self.bot.get.tile_data(name)
        assert style != "letter"
        assert tile_data is not None
        original_style = tile_data["type"]
        original_direction = tile_data["type"]
        
        if style is not None and (meta_level != 0 or original_style != style or  original_direction != direction):
            if original_style == "property":
                # box: position of upper-left coordinate of "inner text" in the larger text tile
                plate, box = self.bot.get.plate(original_direction, wobble)
                plate_alpha = ImageChops.invert(plate.getchannel("A"))
                sprite_alpha = ImageChops.invert(sprite.getchannel("A"))
                alpha = ImageChops.subtract(sprite_alpha, plate_alpha)
                sprite = Image.new("L", sprite.size, color=255)
                sprite.putalpha(alpha)
                sprite = sprite.crop((box[0], box[1], constants.DEFAULT_SPRITE_SIZE + box[0], constants.DEFAULT_SPRITE_SIZE + box[1]))
            if style == "property":
                plate, box = self.bot.get.plate(direction, wobble)
                plate = self.make_meta(plate, meta_level)
                plate_alpha = plate.getchannel("A")
                sprite_alpha = sprite.getchannel("A").crop()
                sprite = ImageChops.add(sprite_alpha, plate_alpha).convert("RGBA")
            else:
                sprite = self.make_meta(sprite.getchannel("A"), meta_level)
        return sprite

    def make_meta(self, img: Image.Image, level: int) -> Image.Image:
        '''Applies a meta filter to an image.'''
        if level > constants.MAX_META_DEPTH:
            raise ValueError(level)
    
        for _ in range(level):
            base = img.crop((-2, -2, img.width + 2, img.height + 2))
            filtered = ImageChops.invert(base).filter(ImageFilter.FIND_EDGES)
            img = filtered.crop((1, 1, filtered.width - 1, filtered.height - 1))
    
        return img

    def save_frames(self, imgs: list[Image.Image], out: str | BinaryIO) -> None:
        '''Saves the images as a gif to the given file or buffer.
        
        If a buffer, this also conveniently seeks to the start of the buffer.
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

def setup(bot: Bot):
    bot.renderer = Renderer(bot)
