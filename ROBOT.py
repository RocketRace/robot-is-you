import discord

from discord.ext  import commands
from discord.http import asyncio
from json         import load
from time         import time

# Sets up the configuration
configFile = open("setup.json")
configuration = load(configFile)

BOT_TOKEN = configuration.get("token")
DEFAULT_ACTIVITY = discord.Game(name=configuration.get("activity"))
COGS = configuration.get("cogs")
PREFIXES = configuration.get("prefixes")
WEBHOOK_ID = configuration.get("webhook")
WEBHOOK_TOKEN = configuration.get("webhook-token")

# Establishes the bot
bot = commands.Bot(command_prefix=PREFIXES, case_insensitive=True, help_command=None, activity=DEFAULT_ACTIVITY)

logger = None

# Loads the modules of the bot
if __name__ == "__main__":
    for cog in COGS:
        bot.load_extension(cog)

@bot.event
async def on_ready():
    logger = await bot.fetch_webhook(int(WEBHOOK_ID))
    msg = discord.Embed(title="READY", type="rich", description="".join([bot.user.mention, " is ready"]), color=0x00ff00)
    await logger.send(content=" ", embed=msg)
    
@bot.event
async def on_disconnect():
    start = time()
    logger = await bot.fetch_webhook(int(WEBHOOK_ID))
    try:
        await bot.wait_for("resumed", timeout=60.0)
    except asyncio.TimeoutError:
        err = discord.Embed(title="Disconnect", type="rich", description="".join([bot.user.mention, " has disconnected"]), color=0xff8800)
    else: 
        err = discord.Embed(title="Resumed", type="rich", description="".join(
            [bot.user.mention, " has resumed. Downtime: ", round(time() - start), " seconds."]), color=0xffff00)
    await logger.send(content=" ", embed=err)

bot.run(BOT_TOKEN, bot = True, reconnect = True)