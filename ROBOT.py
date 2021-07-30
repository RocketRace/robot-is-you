from __future__ import annotations

import json
import logging
import os
import pathlib
import random
import sys
from datetime import datetime
from typing import Iterable

import discord
import jishaku
from discord.ext import commands
from PIL import Image

import auth
import config
from src.constants import DIRECTIONS


class Context(commands.Context):
    async def error(self, msg: str) -> discord.Message:
        await self.message.add_reaction("\u26a0\ufe0f")
        return await self.reply(msg)

    async def send(self, content: str = "", embed: discord.Embed | None = None, **kwargs) -> discord.Message:
        if len(content) > 2000:
            msg = " [...] \n\n (Character limit reached!)"
            content = content[:2000-len(msg)] + msg
        if embed is not None:
            if content:
                return await self.reply(content, embed=embed, **kwargs)
            return await self.reply(embed=embed, **kwargs)
        elif content:
            return await self.reply(content, embed=embed, **kwargs)
        return await self.reply(**kwargs)

class DataAccess:
    '''Means through which most bot data is accessed.
    
    This will be hooked up to a database driver eventually.
    '''
    _tile_data: dict
    _level_tile_data: dict
    _letter_data: dict
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        # this is all temporary until I migrate to a DB
        self._late_init_dict("cache/tiledata.json", "_tile_data")
        self._late_init_dict("config/leveltileoverride.json", "_level_tile_data")
        self.load_letters()

    def load_letters(self) -> None:
        self._letter_data = {}
        prefix = "_0.png"
        for path in pathlib.Path("target/letters").glob("*/*/*/*" + prefix):
            *_, mode, char, width, name = path.parts
            (
                self._letter_data
                .setdefault(mode, {})
                .setdefault(char, {})
                .setdefault(int(width), [])
                .append(name[:-len(prefix)])
            )

    def _late_init_dict(self, path: str, attr: str) -> None:
        with open(path) as fp:
            data = fp.read()
            setattr(self, attr, json.loads(data) if data else {})

    def tile_datas(self) -> Iterable[tuple[str, dict]]:
        '''All them'''
        yield from self._tile_data.items()

    def tile_data(self, tile: str) -> dict | None:
        '''Tile data. Returns None on failure.'''
        return self._tile_data.get(tile)
    
    def level_tile_data(self, tile: str) -> dict | None:
        '''Level tile overrides. Returns None on failure.'''
        return self._level_tile_data.get(tile)

    def plate(self, direction: int | None, wobble: int) -> tuple[Image.Image, tuple[int, int]]:
        '''Plate sprites. Raises FileNotFoundError on failure.'''
        if direction is None:
            return (
                Image.open(f"data/plates/plate_property_0_{wobble+1}.png").convert("RGBA"),
                (0, 0)
            )
        return (
            Image.open(f"data/plates/plate_property{DIRECTIONS[direction]}_0_{wobble+1}.png").convert("RGBA"),
            (3, 3)
        )
    
    def letter_width(self, char: str, mode: str, *, greater_than: int) -> int:
        '''The minimum letter width for the given char of the give mode,
        such that the width is more than the given width.

        Raises KeyError(char) on failure.
        '''
        extras = {
            "*": "asterisk"
        }
        char = extras.get(char, char)
        try:
            return min(width for width in self._letter_data[mode][char] if width > greater_than)
        # given width too large
        except ValueError:
            raise KeyError(char)

    def letter_sprite(self, char: str, mode: str, width: int, wobble: int, *, seed: int | None) -> Image.Image:
        '''Letter sprites. Raises FileNotFoundError on failure.'''
        choices = self._letter_data[mode][char][width]
        if seed is None:
            choice = random.choice(choices)
        else:
            # This isn't uniformly random since `seed` ranges from 0 to 255,
            # but it's "good enough" for me and "random enough" for an observer.
            choice = choices[seed % len(choices)]
        return Image.open(
            f"target/letters/{mode}/{char}/{width}/{choice}_{wobble}.png"
        )

class Bot(commands.Bot):
    '''Custom bot class :)'''
    def __init__(self, *args, cogs: list[str], embed_color: discord.Color, webhook_id: int, prefixes: list[str], **kwargs):
        self.started = datetime.utcnow()
        self.loading = True
        self.exit_code = 0
        self.embed_color = embed_color
        self.webhook_id = webhook_id
        self.prefixes = prefixes
        self.get = DataAccess(self)
        
        super().__init__(*args, **kwargs)
        # has to be after __init__
        for cog in cogs:
            self.load_extension(cog, package="ROBOT")

    async def get_context(self, message: discord.Message) -> Context:
        return await super().get_context(message, cls=Context)

logging.basicConfig(filename=config.log_file, level=logging.WARNING)

# Establishes the bot
bot = Bot(
    # Prefixes
    commands.when_mentioned_or(*config.prefixes) if config.trigger_on_mention else config.prefixes,
    # Other behavior parameters
    case_insensitive=True, 
    activity=discord.Game(name=config.activity), 
    description=config.description,
    # Never mention roles, @everyone or @here
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
    # Only receive message and reaction events
    intents=discord.Intents(messages=True, reactions=True, guilds=True),
    # Disable the member cache
    member_cache_flags=discord.MemberCacheFlags.none(),
    # Disable the message cache
    max_messages=None,
    # Don't chunk guilds
    chunk_guilds_at_startup=False,
    # custom fields
    cogs=config.cogs,
    embed_color=config.embed_color,
    webhook_id=config.webhook_id,
    prefixes=config.prefixes,
)

bot.run(auth.token)
sys.exit(bot.exit_code)
