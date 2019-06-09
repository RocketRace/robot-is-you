import discord
import sys
import traceback

from asyncio      import create_task
from discord.ext  import commands
from json         import load

"""
By EeviePy on GitHub: https://gist.github.com/EvieePy/7822af90858ef65012ea500bcecf1612
"""

class CommandErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = None

    @commands.Cog.listener()
    async def on_error(self, ctx, error):
        if self.logger == None:
            configFile = open("setup.json")
            config = load(configFile)
            if config.get("webhook") != "":
                self.logger = await self.bot.fetch_webhook(int(config.get("webhook")))

        error = getattr(error, 'original', error)
        
        emb = discord.Embed(title="Command Error", color=0xffff00)
        emb.description = str(error)
        chan = "`Direct Message`"
        gui = "Guild: [None]"
        if isinstance(ctx.channel, discord.TextChannel):
            chan = ctx.channel.name
            gui = f"Guild: {ctx.guild.name} (ID:{ctx.guild.id})"
        emb.add_field(name="Error Context", 
                    value="".join([f"Message: `{ctx.message.content}` (ID: {ctx.message.id})\n",
                             f"User: {ctx.author.name}#{ctx.author.discriminator} (ID: {ctx.author.id}\n",
                             f"Channel: #{chan} (ID: {ctx.channel.id})\n", 
                             gui]))

    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """The event triggered when an error is raised while invoking a command.
        ctx   : Context
        error : Exception"""

        if self.logger == None:
            configFile = open("setup.json")
            config = load(configFile)
            if config.get("webhook") != "":
                self.logger = await self.bot.fetch_webhook(int(config.get("webhook")))

        # This prevents any commands with local handlers being handled here in on_command_error.
        if hasattr(ctx.command, 'on_error'):
            return
        
        ignored = (commands.UserInputError) # commands.CommandNotFound, 
        
        # Allows us to check for original exceptions raised and sent to CommandInvokeError.
        # If nothing is found. We keep the exception passed to on_command_error.
        error = getattr(error, 'original', error)
        
        # Constructs the error embed for logging
        emb = discord.Embed(title="Command Error", color=0xffff00)
        emb.description = str(error)
        chan = "`Direct Message`"
        if isinstance(ctx.channel, discord.TextChannel):
            chan = ctx.channel.name
        emb.add_field(name="Error Context", 
                    value="".join([f"Message: `{ctx.message.content}` (ID: {ctx.message.id})\n",
                             f"User: {ctx.author.name}#{ctx.author.discriminator} (ID: {ctx.author.id}\n",
                             f"Channel: #{chan} (ID: {ctx.channel.id})\n", 
                             f"Guild: {ctx.guild.name} (ID:{ctx.guild.id})"]))

        # Anything in ignored will return and prevent anything happening.
        if isinstance(error, ignored):
            return

        elif isinstance(error, commands.DisabledCommand):
            await ctx.send(f'{ctx.command} has been disabled.')
            return await self.logger.send(embed=emb)
        
        elif isinstance(error, commands.CommandOnCooldown):
            if ctx.author.id == self.bot.owner_id:
                return await ctx.reinvoke()
            else:
                await ctx.send(error)
                return await self.logger.send(embed=emb)


        elif isinstance(error, commands.NoPrivateMessage):
            msg = None
            try:
                msg = await ctx.author.send(f'{ctx.command} can not be used in Private Messages.')
            except:
                emb.add_field("Notes", "Could not send private messages to user.")
            await self.logger.send(embed=emb)
            return msg

        # For this error example we check to see where it came from...
        elif isinstance(error, commands.ArgumentParsingError):
            await self.logger.send(embed=emb)
            if ctx.command.name in ["tile", "rule"]:  # Checks the 
                return await ctx.add_reaction("⚠️")

        # All other Errors not returned come here... And we can just print the default TraceBack + log
        await self.logger.send(embed=emb)
        print(f'Ignoring exception in command {ctx.command}:', file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

def setup(bot):
    bot.add_cog(CommandErrorHandler(bot))
