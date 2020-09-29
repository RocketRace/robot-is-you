import asyncio
import discord
import jishaku
import logging
import sys

from datetime     import datetime
from discord.ext  import commands
from json         import load
from timeit       import timeit

# Uses a custom bot class
class BabaBot(commands.Bot):
    # Custom send that sends content in an embed
    # Note that due to AllowedMentions, mentions do not have to be "sanitized"
    async def send(self, ctx, content, embed=None, tts=False, file=None):
        if len(content) > 2000:
            content = content[:1963] + " [...] \n\n (Character limit reached!)"
        if embed is not None:
            return await ctx.send(content, embed=embed)
        segments = content.split("\n")
        title = segments[0]
        description="\n".join(segments[1:])
        if len(title) > 256:
            title = None
            description = "\n".join(segments)
        container = discord.Embed(title=title, description=description, color=self.embed_color)
        await ctx.send(embed=container, tts=tts, file=file)

    # Custom error message implementation
    # Sends the error message. Automatically deletes it after some time.
    async def error(self, ctx, title, content=None):
        description = content if content else None
        embed = discord.Embed(
            title=title, 
            description=description,
            color=self.embed_color
        )
        await ctx.message.add_reaction("⚠️")
        await ctx.send(embed=embed, delete_after=20)

# Sets up the config
with open("config/setup.json") as config_file:
    conf = load(config_file)

logging.basicConfig(filename=conf.get("log_file"), level=logging.WARNING)
default_activity = discord.Game(name=conf.get("activity"))
prefixes = conf.get("prefixes")
bot_trigger = commands.when_mentioned_or(*prefixes) if conf.get("trigger_on_mention") else prefixes

default_mentions = discord.AllowedMentions(everyone=False, roles=False)
intents = discord.Intents(messages=True, reactions=True)
member_cache = discord.MemberCacheFlags.none()
# Establishes the bot
bot = BabaBot(
    # Prefixes
    bot_trigger,
    # Other behavior parameters
    case_insensitive=True, 
    activity=default_activity, 
    owner_id=conf.get("owner_id"),
    description=conf.get("description"),
    # Never mention roles, @everyone or @here
    allowed_mentions=default_mentions, 
    # Only receive message and reaction events
    intents=intents,
    # Disable the member cache
    member_cache_flags=member_cache,
    # Disable the message cache
    max_messages=None,
    # Don't chunk guilds
    chunk_guilds_at_startup=False
)

bot.started = datetime.utcnow()
bot.loading = False
bot.embed_color = conf.get("embed_color")
bot.webhook_id = conf.get("webhook_id")
bot.prefixes = prefixes
bot.exit_code = 0

# Loads the modules of the bot
for cog in conf.get("cogs"):
    bot.load_extension(cog)

# Run
with open(conf.get("auth_file")) as f:
    auth_conf = load(f)

bot.run(auth_conf.get("token"))

sys.exit(bot.exit_code)