import discord
import itertools

from discord.ext  import commands
from discord.http import asyncio
from json         import load
from time         import time

# Sets up the configuration
configuration = None
with open("setup.json") as configFile:
    configuration = load(configFile)

BOT_TOKEN = configuration.get("token")
DEFAULT_ACTIVITY = discord.Game(name=configuration.get("activity"))
COGS = configuration.get("cogs")
PREFIXES = configuration.get("prefixes")
WEBHOOK_ID = configuration.get("webhook")
WEBHOOK_TOKEN = configuration.get("webhook-token")
EMBED_COLOR = configuration.get("color")

# Uses a custom bot class
class BabaBot(commands.Bot):
    def __init__(self, command_prefix, webhook_id, embed_color, help_command=None, description=None, **options):
        self.loading = False
        
        self.embedColor = embed_color
        self.webhookId = webhook_id
        super().__init__(command_prefix, help_command=help_command, description=description, **options)
    
    # Custom send that sends content in an embed
    # Sanitizes input, so no mention abuse can occur
    async def send(self, ctx, content, embed=None, tts=False, file=None):
        sanitized = discord.utils.escape_mentions(content)
        if len(sanitized) > 1000:
            sanitized = sanitized[:1000] + " [...] \n\n (Character limit reached!)"
        if embed is not None:
            await ctx.send(sanitized, embed=embed)
        else:
            segments = sanitized.split("\n")
            title = segments[0]
            description="\n".join(segments[1:])
            if len(title) > 256:
                title = None
                description = "\n".join(segments)
            container = discord.Embed(title=title, description=description, color=self.embedColor)
            await ctx.send(" ", embed=container, tts=tts, file=file)


# Establishes the bot
bot = BabaBot(PREFIXES, WEBHOOK_ID, EMBED_COLOR, case_insensitive=True, activity=DEFAULT_ACTIVITY, owner_id = 156021301654454272)

# Loads the modules of the bot
if __name__ == "__main__":
    for cog in COGS:
        bot.load_extension(cog)

# Allows for the code to be reloaded without reloading the bot
@bot.command(hidden=True)
@commands.is_owner()
async def reloadcog(ctx, cog: str):
    if cog == "all":
        extensions = [a for a in bot.extensions.keys()]
        for extension in extensions:
            bot.reload_extension(extension)
        await ctx.send("Reloaded all extensions.")
    elif cog in bot.extensions.keys():
        bot.reload_extension("cogs." + cog)
        await ctx.send(f"Reloaded extension `{cog}` from `cogs/{cog}.py`.")
    

bot.run(BOT_TOKEN, bot = True, reconnect = True)