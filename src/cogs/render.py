from __future__ import annotations

import collections
import random
import string
import zipfile
from io import BytesIO
from typing import TYPE_CHECKING, BinaryIO

import numpy as np
from PIL import Image, ImageChops, ImageFilter

from .. import constants, errors
from ..tile import FullTile, Grid, ReadyTile
from ..utils import cached_open
from ..save_transparent_gif import save_transparent_gif

if TYPE_CHECKING:
    from ...ROBOT import Bot


class Renderer:
    '''This class exposes various image rendering methods. 
    Some of them require metadata from the bot to function properly.
    '''
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    def recolor(self, sprite: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
        '''Apply rgb color multiplication (0-255)'''
        r,g,b = rgb
        arr = np.asarray(sprite, dtype='float64')
        arr[..., 0] *= r / 256
        arr[..., 1] *= g / 256
        arr[..., 2] *= b / 256
        return Image.fromarray(arr.astype('uint8'))

    async def render(
        self,
        grid: Grid[ReadyTile],
        *,
        grid_size: tuple[int, int],
        duration: int,
        palette: str = "default",
        images: list[str] | None = None,
        image_source: str = constants.BABA_WORLD,
        out: str | BinaryIO = "target/renders/render.gif",
        delay: int = 200,
        frame_count: int = 3,
        background: tuple[int, int] | None = None,
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
        if background is not None:
            background_color = palette_img.getpixel(background)
        else:
            background_color = (0, 0, 0, 0)
        imgs: list[Image.Image] = []
        # This is appropriate padding, no sprites can go beyond it
        padding = constants.DEFAULT_SPRITE_SIZE
        width, height = grid_size
        for _ in range(duration):
            for frame in range(frame_count):
                img_width = width * constants.DEFAULT_SPRITE_SIZE + 2 * padding
                img_height =  height * constants.DEFAULT_SPRITE_SIZE + 2 * padding

                if images and image_source is not None:
                    img = Image.new("RGBA", (img_width, img_height))
                    # for loop in case multiple background images are used (i.e. baba's world map)
                    for image in images:
                        try:
                            overlap = Image.open(f"data/images/{image_source}/{image}_{frame + 1}.png").convert("RGBA") # bg images are 1-indexed
                        except FileNotFoundError:
                            # no animations, default to frame 1
                            overlap = Image.open(f"data/images/{image_source}/{image}_1.png").convert("RGBA") # bg images are 1-indexed
                        img.paste(overlap, (padding, padding), mask=overlap)
                # bg color
                elif background is not None:
                    img = Image.new("RGBA", (img_width, img_height), color=background_color)
                # neither
                else: 
                    img = Image.new("RGBA", (img_width, img_height))
                imgs.append(img)
        
        # keeping track of the amount of padding we can slice off
        pad_r=pad_u=pad_l=pad_d=0
        for (x, y, t), stack in grid.items():
            for tile in stack:
                if tile.frames is None:
                    continue
                for frame, sprite in enumerate(tile.frames[:frame_count]):
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
                        alpha = sprite.getchannel("A")
                    
                    alpha = sprite.getchannel("A")
                    if tile.mask_alpha:
                        sprite = Image.new("RGBA", sprite.size, background_color)
                        alpha = ImageChops.invert(alpha)
                    elif tile.cut_alpha:
                        sprite = Image.new("RGBA", sprite.size, background_color)

                    imgs[t * frame_count + frame].paste(
                        sprite, 
                        (
                            x * constants.DEFAULT_SPRITE_SIZE + padding - x_offset,
                            y * constants.DEFAULT_SPRITE_SIZE + padding - y_offset
                        ), 
                        mask=alpha
                    )

        outs = []
        for img in imgs:
            img = img.crop((padding - pad_l, padding - pad_u, img.width - padding + pad_r, img.height - padding + pad_d))
            if upscale:
                img = img.resize((2 * img.width, 2 * img.height), resample=Image.Resampling.NEAREST)
            outs.append(img)

        self.save_frames(
            outs,
            out,
            delay=delay,
            extra_out=extra_out,
            extra_name=extra_name
        )

    async def render_full_tile(self,
        tile: FullTile,
        *,
        position: tuple[int, int, int],
        palette_img: Image.Image,
        random_animations: bool = False,
        sprite_cache: dict[str, Image.Image]
    ) -> ReadyTile:
        '''woohoo'''
        if tile.empty:
            return ReadyTile(None)
        out = []
        x, y, _ = position
        for frame in range(3):
            wobble = (11 * x + 13 * y + frame) % 3 if random_animations else frame
            if tile.custom:
                sprite = await self.generate_sprite(
                    tile.name,
                    style=tile.custom_style or "noun",
                    direction=tile.custom_direction,
                    meta_level=tile.meta_level,
                    face=tile.face,
                    blank=tile.blank,
                    wobble=wobble,
                )
            else:
                path_fallback = None
                if tile.name in ("icon",):
                    path = f"data/sprites/{constants.BABA_WORLD}/{tile.name}.png"
                elif tile.name in ("smiley", "hi") or tile.name.startswith("icon"):
                    path = f"data/sprites/{constants.BABA_WORLD}/{tile.name}_1.png"
                elif tile.name == "default":
                    path = f"data/sprites/{constants.BABA_WORLD}/default_{wobble + 1}.png"
                else:
                    source, sprite_name = tile.sprite
                    path = f"data/sprites/{source}/{sprite_name}_{tile.variant_number}_{wobble + 1}.png"
                    path_fallback = f"data/sprites/{source}/{sprite_name}_{tile.variant_fallback}_{wobble + 1}.png"
                try:
                    sprite = cached_open(path, cache=sprite_cache, fn=Image.open).convert("RGBA")
                except FileNotFoundError:
                    if path_fallback is not None:
                        sprite = cached_open(path_fallback, cache=sprite_cache, fn=Image.open).convert("RGBA")
                    else:
                        raise
                
                sprite = await self.apply_options_name(
                    tile.name,
                    sprite,
                    style=tile.custom_style,
                    direction=tile.custom_direction,
                    meta_level=tile.meta_level,
                    face=tile.face,
                    blank=tile.blank,
                    wobble=wobble,
                )
            # Color conversion
            rgb = tile.color_rgb if tile.color_rgb is not None else palette_img.getpixel(tile.color_index)
            sprite = self.recolor(sprite, rgb)
            out.append(sprite)
        f0, f1, f2 = out
        return ReadyTile((f0, f1, f2), tile.mask_alpha, tile.cut_alpha)

    async def render_full_tiles(
        self,
        grid: Grid[FullTile],
        *,
        palette: str = "default",
        random_animations: bool = False
    ) -> Grid[ReadyTile]:
        '''Final individual tile processing step'''
        sprite_cache = {}
        palette_img = Image.open(f"data/palettes/{palette}.png").convert("RGB")

        out = {}
        for index, stack in grid.items():
            out[index] = [
                await self.render_full_tile(
                    tile,
                    position=index,
                    palette_img=palette_img,
                    random_animations=random_animations,
                    sprite_cache=sprite_cache
                )
                for tile in stack
            ]
        return out

    async def generate_sprite(
        self,
        text: str,
        *,
        style: str,
        direction: int | None,
        meta_level: int,
        face: bool,
        blank: bool,
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
        seed_digits = [(seed >> 8 * i ) | 0b11111111 for i in range(len(raw))]
        
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
        
        if len(raw) == 1 and raw in string.ascii_letters + string.digits:
            sprite = Image.open(f"data/sprites/baba/text_{raw}_0_{wobble + 1}.png").convert("RGBA")
            return self.apply_options(
                sprite, 
                original_style="noun",
                style=style,
                original_direction=None,
                direction=direction,
                meta_level=meta_level,
                face=face,
                blank=blank,
                wobble=wobble
            )

        width_cache: dict[str, list[int]] = {}
        for c in raw:
            rows = await self.bot.db.conn.fetchall(
                '''
                SELECT char, width FROM letters
                WHERE char == ? AND mode == ?;
                ''',
                c, mode
            )

            for row in rows:
                char, width = row
                width_cache.setdefault(char, []).append(width)

        def width_greater_than(c: str, w: int = 0) -> int:
            try:
                return min(width for width in width_cache[c] if width > w)
            except ValueError:
                raise KeyError

        # fetch the minimum possible widths first
        try:
            widths: list[int] = [width_greater_than(c) for c in raw]
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
                new_width = width_greater_than(raw[i], old_width)
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
        for c, seed_digit, width in zip(raw, seed_digits, widths):
            l_rows = await self.bot.db.conn.fetchall(
                # fstring use safe
                f'''
                SELECT char, width, sprite_{int(wobble)} FROM letters
                WHERE char == ? AND mode == ? AND width == ?
                ''',
                c, mode, width
            )
            options = list(l_rows)
            char, width, letter_sprite = options[seed_digit % len(options)]
            buf = BytesIO(letter_sprite)
            letters.append(Image.open(buf))

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
            face=face,
            blank=blank,
            wobble=wobble
        )

    async def apply_options_name(
        self,
        name: str,
        sprite: Image.Image,
        *,
        style: str | None,
        direction: int | None,
        meta_level: int,
        face: bool,
        blank: bool,
        wobble: int
    ) -> Image.Image:
        '''Takes an image, taking tile data from its name, and applies the given options to it.'''
        tile_data = await self.bot.db.tile(name)
        assert tile_data is not None
        original_style = constants.TEXT_TYPES[tile_data.text_type]
        original_direction = tile_data.text_direction
        if style is None:
            style = original_style
        try:
            return self.apply_options(
                sprite,
                original_style=original_style,
                style=style,
                original_direction=original_direction,
                direction=direction,
                meta_level=meta_level,
                face=face,
                blank=blank,
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
        face: bool,
        blank: bool,
        wobble: int
    ):
        '''Takes an image, with or without a plate, and applies the given options to it.'''
        if face:
            pixel_counts = collections.Counter((r, g, b) for r, g, b, a in sprite.getdata() if a)
            color, _ = pixel_counts.most_common()[-1]
            lut_r = [0 for _ in range(256)]
            lut_g = [0 for _ in range(256)]
            lut_b = [0 for _ in range(256)]
            lut_a = [0 for _ in range(256)]
            lut_r[color[0]] = lut_g[color[1]] = lut_b[color[2]] = 255
            lut_a[255] = 255
            r, g, b, _ = sprite.split()
            alpha = Image.merge("RGB", (r.point(lut_g), g.point(lut_g), b.point(lut_b))).convert("L")
            lut_r[color[0]] = color[0]
            lut_g[color[1]] = color[1]
            lut_b[color[2]] = color[2]
            sprite = Image.merge("RGBA", (r.point(lut_g), g.point(lut_g), b.point(lut_b), alpha))

        if blank:
            new = Image.new("RGB", sprite.size, (255, 255, 255))
            new.putalpha(sprite.getchannel("A"))
            sprite = new

        if (
            meta_level != 0 or 
            original_style != style or (
                style == "property" and 
                original_direction != direction
            )
        ):
            if original_style == "property":
                # box: position of upper-left coordinate of "inner text" in the larger text tile
                plate, box = self.bot.db.plate(original_direction, wobble)
                plate_alpha = ImageChops.invert(plate.getchannel("A"))
                sprite_alpha = ImageChops.invert(sprite.getchannel("A"))
                alpha = ImageChops.subtract(sprite_alpha, plate_alpha)
                sprite = Image.merge("RGBA", (alpha, alpha, alpha, alpha))
                sprite = sprite.crop((box[0], box[1], constants.DEFAULT_SPRITE_SIZE + box[0], constants.DEFAULT_SPRITE_SIZE + box[1]))
            if style == "property":
                if sprite.height != constants.DEFAULT_SPRITE_SIZE or sprite.width != constants.DEFAULT_SPRITE_SIZE:
                    raise ValueError(sprite.size)
                plate, box = self.bot.db.plate(direction, wobble)
                plate = self.make_meta(plate, meta_level)
                plate_alpha = plate.getchannel("A")
                sprite_alpha = sprite.getchannel("A").crop(
                    (-meta_level, -meta_level, sprite.width + meta_level, sprite.height + meta_level)
                )
                sprite_alpha = sprite_alpha.crop(
                    (-box[0], -box[0], sprite_alpha.width + box[0], sprite_alpha.height + box[1])
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
        elif level % 2 == 1 and level != 1:
            blank = Image.new("RGBA", orig.size)
            base.paste(blank, (level, level), mask=orig)
        
        return base

    def save_frames(
        self,
        imgs: list[Image.Image],
        out: str | BinaryIO,
        delay: int = 200,
        extra_out: str | BinaryIO | None = None,
        extra_name: str | None = None
    ) -> None:
        '''Saves the images as a gif to the given file or buffer.
        
        If a buffer, this also conveniently seeks to the start of the buffer.

        If extra_out is provided, the frames are also saved as a zip file there.
        '''
        # Pillow has a longstanding bug with transparency indices in gifs
        save_transparent_gif(imgs, delay, out)
        if not isinstance(out, str):
            out.seek(0)
        if extra_name is not None and extra_out is not None:
            file = zipfile.PyZipFile(extra_out, "x")
            for i, img in enumerate(imgs):
                buffer = BytesIO()
                img.save(buffer, "PNG")
                file.writestr(f"{extra_name}_{i//3}_{(i%3)+1}.png", buffer.getvalue())
            file.close()

async def setup(bot: Bot):
    bot.renderer = Renderer(bot)
