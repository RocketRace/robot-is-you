from __future__ import annotations

import logging
from src.cogs.operations import OperationMacros

import aiohttp
from src import synchronization
import traceback
import asyncio
from datetime import datetime
from typing import Any, Coroutine

import discord
import jishaku
from discord.ext import commands

import auth
import config
from src.constants import MAXIMUM_GUILD_THRESHOLD, GAMEOVER_GUILD_THRESHOLD
from src.db import Database
from src.cogs.render import Renderer
from src.cogs.variants import VariantHandlers

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
                return await super().send(content, embed=embed, **kwargs)
            return await super().send(embed=embed, **kwargs)
        elif content:
            return await super().send(content, embed=embed, **kwargs)
        return await super().send(**kwargs)

class Bot(commands.Bot):
    '''Custom bot class :)'''
    db: Database
    variant_handlers: VariantHandlers
    operation_macros: OperationMacros
    renderer: Renderer
    def __init__(
        self, 
        command_prefix,
        *,
        cogs: list[str], 
        embed_color: discord.Color, 
        webhook_url: str,
        prefixes: list[str],
        db_path: str, 
        instance_id: int,
        event_queue: asyncio.Queue[synchronization.CallbackEvent],
        original_id: int,
        **kwargs
    ):
        self.started = datetime.utcnow()
        self.loading = True
        self.exit_code = 0
        self.embed_color = embed_color
        self.webhook_url = webhook_url
        self.prefixes = prefixes
        self.db = Database()
        self.db_path = db_path
        self.instance_id = instance_id
        self.event_queue = event_queue
        self.original_id = original_id
        self.cog_names = cogs
        
        super().__init__(command_prefix, **kwargs)
    
    async def setup_hook(self) -> None:
        for cog in self.cog_names:
            await self.load_extension(cog, package="ROBOT")
        return await super().setup_hook()

    async def request(self, event: synchronization.CallbackEvent):
        '''Send a request to the event manager of the bot instances.'''
        await self.event_queue.put(event)

    async def get_context(self, message: discord.Message) -> Context:
        return await super().get_context(message, cls=Context)

    async def close(self) -> None:
        await self.db.close()
        await self.session.close()
        await super().close()

    async def on_ready(self) -> None:
        print(f"{self.user}: Logged in!")
        print(f"{self.user}: Invite: {discord.utils.oauth_url(str(self.user.id))}")
        await self.db.connect(self.db_path)
        if MAXIMUM_GUILD_THRESHOLD < len(self.guilds) < GAMEOVER_GUILD_THRESHOLD:
            print(f"{self.user}: WARNING: Dangerously close to the guild limit, purging...")
            guild_ids: set[int] = {row[0] for row in await self.db.conn.fetchall(
                '''SELECT guild_id FROM guilds WHERE bot_id == ?;'''
            )}
            count = len(self.guilds) - MAXIMUM_GUILD_THRESHOLD
            for guild in self.guilds:
                if guild.id not in guild_ids:
                    await guild.leave()
                    count -= 1
                if count == 0:
                    break
            print(f"{self.user}: Purged {count} guilds.")

        await self.db.conn.executemany(
            '''
            INSERT INTO guilds VALUES (?, ?)
            ON CONFLICT (guild_id) DO NOTHING;
            ''',
            ((guild.id, self.user.id) for guild in self.guilds)
        )
        print(f"{self.user}: Established database connection!")
        self.session = aiohttp.ClientSession()
        print(f"{self.user}: Client session ready!")
    
    async def start_with_exit_code(self, token: str) -> int:
        await self.start(token)
        return self.exit_code

logging.basicConfig(filename=config.log_file, level=logging.WARNING)

bots: list[Bot] = []
starters: list[Coroutine[Any, Any, int]] = []

mpsc_queue = asyncio.Queue()

async def shared_event_handler(event_queue: asyncio.Queue[synchronization.CallbackEvent]) -> int:
    while True:
        item = await event_queue.get()
        event = item.event
        callback = item.callback
        try:
            if isinstance(event, synchronization.CogRefreshEvent):
                cog = event.cog
                if cog is None:
                    for bot in bots:
                        # construct a list to avoid iterating over a dict as it's mutated
                        for ext in list(bot.extensions):
                            await bot.reload_extension(ext)
                else:
                    for bot in bots:
                        await bot.reload_extension(cog)
                await callback()
        except:
            traceback.print_exc()

for i, token in enumerate(auth.tokens):
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
        intents=discord.Intents(messages=True, reactions=True, guilds=True, message_content=True),
        # Disable the member cache
        member_cache_flags=discord.MemberCacheFlags.none(),
        # Disable the message cache
        max_messages=None,
        # Don't chunk guilds
        chunk_guilds_at_startup=False,
        # for hot reloading
        cogs=config.cogs,
        embed_color=config.embed_color,
        # display only
        prefixes=config.prefixes,
        db_path=config.db_path,
        # synchronization
        instance_id=i,
        event_queue=mpsc_queue,
        # logging
        webhook_url=auth.webhook_url,
        original_id=config.original_id
    )
    bots.append(bot)
    starters.append(bot.start_with_exit_code(token))


async def main() -> int:
    events = asyncio.create_task(shared_event_handler(mpsc_queue))
    tasks = [asyncio.create_task(starter) for starter in starters]
    try:
        for returner in asyncio.as_completed(tasks):
            return await returner
        else:
            raise RuntimeError("There are no bots to run")
    finally:
        print("Shutting down bots...")
        events.cancel()
        await asyncio.gather(
            *(bot.close() for bot in bots if not bot.is_closed())
        )

exit_code = 0
try:
    x = asyncio.run(main())
except KeyboardInterrupt:
    exit_code = 1
finally:
    exit(exit_code)
