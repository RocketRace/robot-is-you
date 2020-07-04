import discord
import sys
import traceback

from asyncio      import create_task
from discord.ext  import commands

"""
By EeviePy on GitHub: https://gist.github.com/EvieePy/7822af90858ef65012ea500bcecf1612
"""

class CommandErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.webhook_id = bot.webhook_id
        self.logger = None

    async def setup_logger(self, webhook_id):
        return await self.bot.fetch_webhook(webhook_id)

    @commands.Cog.listener()
    async def on_error(self, ctx, error):
        if self.logger is None:
            self.logger = await self.setup_logger(self.webhook_id)

        error = getattr(error, 'original', error)
        
        emb = discord.Embed(title="Error", color=0xffff00)
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
                gui
            ])
        )

    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """The event triggered when an error is raised while invoking a command.
        ctx   : Context
        error : Exception"""

        if self.logger is None:
            self.logger = await self.setup_logger(self.webhook_id)

        # This prevents any commands with local handlers being handled here in on_command_error.
        if hasattr(ctx.command, 'on_error'):
            return
        
        ignored = (commands.CommandNotFound, commands.NotOwner, commands.CheckFailure) 
        whitelist = ()
        
        # Allows us to check for original exceptions raised and sent to CommandInvokeError.
        # If nothing is found. We keep the exception passed to on_command_error.
        error = getattr(error, 'original', error)
        
        # Constructs the error embed for logging
        emb = discord.Embed(title="Command Error", color=0xffff00)
        emb.description = str(error)

        # Adds embed fields
        # Bot
        if self.bot.user: # tautology but fits the scheme
            ID = self.bot.user.id
            name = self.bot.user.display_name
        # Message
        if ctx.message:
            ID = ctx.message.id
            content = ctx.message.content 
            if len(content) > 1024: # Only use the first 1000 characters, avoid 1024 char value limits
                content = content[1000] + "`...`"
            formatted = f"ID: {ID}\nContent: `{content}`" 
            emb.add_field(name="Message", value=formatted)
        # Channel
        if isinstance(ctx.channel, discord.TextChannel):
            ID = ctx.channel.id
            name = ctx.channel.name
            nsfw = "[NSFW Channel]" if ctx.channel.is_nsfw() else ""
            news = "[News Channel]" if ctx.channel.is_news() else ""
            formatted = f"ID: {ID}\nName: {name}\n{nsfw} {news}"
            emb.add_field(name="Channel",value=formatted)
        # Guild (if in a guild)
        if ctx.guild:
            ID = ctx.guild.id
            name = ctx.guild.name
            member_count = ctx.guild.member_count
            formatted = f"ID: {ID}\nName: {name}\nMember count: {member_count}"
            emb.add_field(name="Guild", value=formatted)
        # Author (DM information if any)
        if ctx.author:
            ID = ctx.author.id
            name = ctx.author.name
            discriminator = ctx.author.discriminator
            nick = f"({ctx.author.nick})" if ctx.guild else ""
            DM = "Message Author" if ctx.guild else "Direct Message"
            formatted = f"ID: {ID}\nName: {name}#{discriminator} ({nick})"
            emb.add_field(name=DM, value=formatted)
        # Message link
        if all([ctx.guild, ctx.channel, ctx.message]):
            guild_ID = ctx.guild.id
            channel_ID = ctx.channel.id
            message_ID = ctx.message.id
            formatted = f"[Jump to message](https://discordapp.com/channels/{guild_ID}/{channel_ID}/{message_ID})"
            emb.add_field(name="Jump", value=formatted)

        # Anything in ignored will return and prevent anything happening.
        if isinstance(error, whitelist):
            pass
        elif isinstance(error, ignored):
            return

        if isinstance(error, commands.CommandOnCooldown):
            if ctx.author.id == self.bot.owner_id:
                return await ctx.reinvoke()
            else:
                await self.bot.error(ctx, str(error))
                return await self.logger.send(embed=emb)

        elif isinstance(error, commands.DisabledCommand):
            await self.bot.error(ctx, f'{ctx.command} has been disabled.')
            return await self.logger.send(embed=emb)

        elif isinstance(error, commands.NoPrivateMessage):
            try:
                await self.bot.error(ctx.author, f'{ctx.command} can not be used in Private Messages.')
            except:
                emb.add_field(name="Notes", value="Could not send private messages to user.")
            return await self.logger.send(embed=emb)

        elif isinstance(error, commands.ExpectedClosingQuoteError):
            return await self.bot.error(ctx, f"Expected closing quotation mark `{error.close_quote}`.")
        
        elif isinstance(error, commands.InvalidEndOfQuotedStringError):
            return await self.bot.error(ctx, f"Expected a space after a quoted string, got `{error.char}` instead.")
        
        elif isinstance(error, commands.UnexpectedQuoteError):
            return await self.bot.error(ctx, f"Got unexpected quotation mark `{error.quote}` inside a string.")

        elif isinstance(error, commands.ArgumentParsingError):
            await self.logger.send(embed=emb)
            return await self.bot.error(ctx, "Invalid function arguments provided.")

        elif isinstance(error, commands.MissingRequiredArgument):
            return await self.bot.error(ctx, "Required arguments are missing.")

        elif isinstance(error, discord.HTTPException):
            if error.status == 400:
                return await self.bot.error(ctx, "This action could not be performed.")
            if error.status == 429:
                return await self.bot.error(ctx, "We're being ratelimited. Try again later.")
            if error.status == 401:
                return await self.bot.error(ctx, "This action cannot be performed.")
            return await self.bot.error(ctx, "There was an error while processing this request.")
        
        # All other Errors not returned come here... And we can just print the default TraceBack + log
        await self.bot.error(ctx, f"An exception occurred: {type(error)}", f"{error}\n{''.join(traceback.format_tb(error.__traceback__))}")
        await self.logger.send(embed=emb)
        print(f'Ignoring exception in command {ctx.command}:', file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

def setup(bot):
    bot.add_cog(CommandErrorHandler(bot))
