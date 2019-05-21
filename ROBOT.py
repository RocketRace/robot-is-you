import discord

from discord.ext import commands
from json        import load

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
    msg = discord.Embed(title="READY", type="rich", description="Bot is ready", color=0x00ff00)
    await logger.send(content=" ", embed=msg)
    
@bot.event
async def on_disconnect():
    logger = await bot.fetch_webhook(int(WEBHOOK_ID))
    err = discord.Embed(title="Disconnect", type="rich", description="Bot disconnected", color=0xff0000)
    await logger.send(content=" ", embed=err)

bot.run(BOT_TOKEN, bot = True, reconnect = True)