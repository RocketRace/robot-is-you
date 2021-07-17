from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any, Coroutine, Optional, TypeVar

import discord
from discord.ext import commands
from PIL import Image

if TYPE_CHECKING:
    from .cogs.render import Renderer

class Context(commands.Context):
    async def error(self, msg: str) -> discord.Message: ...
    async def send(self, content: str="", embed: Optional[discord.Embed] = None, **kwargs) -> discord.Message: ...

class DataAccess:
    bot: Bot
    _tile_data: dict
    def __init__(self, bot: Bot) -> None:...
    def tile_data(self, tile: str) -> dict | None:...
    def level_tile_data(self, tile: str) -> dict | None:...
    def plate(self, direction: int | None, wobble: int) -> tuple[Image.Image, tuple[int, int]]:...

class Bot(commands.Bot):
    get: DataAccess
    cogs: list[str]
    embed_color: discord.Color
    webhook_id: int
    prefixes: list[str]
    exit_code: int
    loading: bool
    started: datetime.datetime
    renderer: Renderer
    def __init__(self, *args, cogs: list[str], embed_color: discord.Color, webhook_id: int, prefixes: list[str], exit_code: int = 0, **kwargs):...
    async def get_context(self, message: discord.Message) -> Coroutine[Any, Any, Context]:...
    def get_tile(self, tile: str) -> dict | None:...
