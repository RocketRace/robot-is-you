import discord
import itertools

from discord.ext  import commands
from discord.http import asyncio
from json         import load
from time         import time

# Custom help command implementation
class PrettyHelpCommand(commands.DefaultHelpCommand):
    async def send_pages(self):
        # Overwrite the send method to send each page in an embed instead
        destination = self.get_destination()
        for page in self.paginator.pages:
            formatted = discord.Embed(description=page, color=15335523)
            await destination.send(" ", embed=formatted)

    def add_indented_commands(self, commands, *, heading, max_size=None):
        if not commands:
            return

        self.paginator.add_line()    
        self.paginator.add_line(heading)
        max_size = max_size or self.get_max_size(commands)

        for command in commands:
            name = command.name
            self.paginator.add_line(self.shorten_text("\u00a0\u00a0\u00a0`" + name + "`"))
            self.paginator.add_line(self.shorten_text(command.short_doc))

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot

        if bot.description:
            # <description> portion
            self.paginator.add_line(bot.description, empty=True)

        def get_category(command, *, no_category='\u200b**{0.no_category}**'.format(self)):
            cog = command.cog
            return "**" + cog.qualified_name + '**' if cog is not None else no_category

        filtered = await self.filter_commands(bot.commands, sort=True, key=get_category)
        max_size = self.get_max_size(filtered)
        to_iterate = itertools.groupby(filtered, key=get_category)

        # Now we can add the commands to the page.
        for category, commands in to_iterate:
            commands = sorted(commands, key=lambda c: c.name) if self.sort_commands else list(commands)
            self.add_indented_commands(commands, heading=category, max_size=max_size)

        note = self.get_ending_note()
        if note:
            self.paginator.add_line()
            self.paginator.add_line(note)

        await self.send_pages()

    def get_ending_note(self):
        """Returns help command's ending note. This is mainly useful to override for i18n purposes."""
        command_name = self.invoked_with
        return "*Type `{0}{1} command` for more info on a command.*".format(self.clean_prefix, command_name)

    def get_command_signature(self, command):
        parent = command.full_parent_name
        if len(command.aliases) > 0:
            aliases = '|'.join(command.aliases)
            fmt = '[%s|%s]' % (command.name, aliases)
            if parent:
                fmt = parent + ' ' + fmt
            alias = fmt
        else:
            alias = command.name if not parent else parent + ' ' + command.name

        return '`%s%s %s`' % (self.clean_prefix, alias, command.signature)

class MetaCog(commands.Cog, name="Other Commands"):
    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        # Sets up the help command
        bot.help_command = PrettyHelpCommand(**dict(paginator=commands.Paginator(prefix="", suffix="")))
        bot.help_command.cog = self

    # Check if the bot is loading, and that the current guild is not r/surrealmemes 
    async def cog_check(self, ctx):
        return self.bot.get_cog("Admin").notLoading and ctx.channel.guild.id != 294479294040768524

    @commands.Cog.listener
    async def on_disconnect(self):
        start = time()
        try:
            await self.bot.wait_for("ready", timeout=5.0)
        except asyncio.TimeoutError:
            err = discord.Embed(
                title="Disconnect", 
                type="rich", 
                description="".join([self.bot.user.mention, " has disconnected"]), 
                color=0xff8800)
        else: 
            err = discord.Embed(
                title="Resumed", 
                type="rich", 
                description="".join([self.bot.user.mention, " has resumed. Downtime: ", str(round(time() - start, 2)), " seconds."]), 
                color=0xffff00)
        logger = await self.bot.fetch_webhook(594692503014473729)
        await logger.send(content=" ", embed=err)
    
    def cog_unload(self):
        self.bot.help_command = self._original_help_command

def setup(bot):
    bot.add_cog(MetaCog(bot))
