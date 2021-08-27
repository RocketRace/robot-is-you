from __future__ import annotations

import discord
from discord.ext import commands

class Context(commands.Context):
    async def error(self, msg: str) -> discord.Message: ...
    async def send(self, content: str="", embed: discord.Embed | None = None, **kwargs) -> discord.Message: ...
