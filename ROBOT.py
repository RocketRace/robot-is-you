import discord
import logging

from discord.ext import commands
from json        import load

# Sets up logging 
# logging.basicConfig(filename="log.txt", level=20, format="%(asctime)s - %(levelname)s - %(message)s") 

# Sets up the configuration
configFile = open("setup.json")
configuration = load(configFile)

BOT_TOKEN = configuration.get("token")
DEFAULT_ACTIVITY = discord.Game(name=configuration.get("activity"))
COGS = configuration.get("cogs")

# Establishes the bot
bot = commands.Bot(command_prefix=["+"], case_insensitive=True, help_command=None, activity=DEFAULT_ACTIVITY)

# Loads the modules of the bot
if __name__ == "__main__":
    for cog in COGS:
        bot.load_extension(cog)

# Basic bot events
@bot.event
async def on_connect():
    logging.info("Connected to Discord.")

@bot.event
async def on_ready():
    logging.info("Client caches filled. Ready.")

@bot.event
async def on_command_error(ctx, error, *args):
    print(error)
    print(args)
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send("".join(["⚠️ " + error]))

bot.run(BOT_TOKEN, bot = True, reconnect = True)
