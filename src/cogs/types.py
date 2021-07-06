from __future__ import annotations
import datetime
from typing import Any, Coroutine, Optional
import discord
from discord.ext import commands

class Context(commands.Context):
    async def error(self, msg: str) -> discord.Message: ...
    async def send(self, content: str="", embed: Optional[discord.Embed] = None, **kwargs) -> discord.Message: ...

class Bot(commands.Bot):
    cogs: list[str]
    embed_color: discord.Color
    webhook_id: int
    prefixes: list[str]
    exit_code: int
    loading: bool
    started: datetime.datetime
    def __init__(self, *args, cogs: list[str], embed_color: discord.Color, webhook_id: int, prefixes: list[str], exit_code: int = 0, **kwargs):...
    async def get_context(self, message: discord.Message) -> Coroutine[Any, Any, Context]:...