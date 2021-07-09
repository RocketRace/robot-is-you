from __future__ import annotations

import logging
import sys
from datetime import datetime

import discord
import jishaku
from discord.ext import commands

import auth
import config

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
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._tile_data = {}

    def tile_data(self, tile: str) -> dict | None:
        '''Tile data'''
        return self.bot.get_cog("Admin").tile_data.get(tile)
    
    def level_tile_data(self, tile: str) -> dict | None:
        '''Level tile overrides'''

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
