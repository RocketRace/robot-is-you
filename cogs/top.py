# -*- coding: utf-8 -*-

from discord.ext import commands, tasks
import discord
import dbl
import traceback

class DBLCog(commands.Cog):
    '''
    Handle Top.gg guild count posting
    '''
    @tasks.loop(minutes=30)
    async def update_stats(self):
        try:
            await self.dblpy.post_guild_count()
        except Exception as e:
            traceback.print_exception(type(e), e, e.__traceback__)

    @update_stats.before_loop
    async def prepare(self):
        await self.bot.wait_until_ready()

    def __init__(self, bot):
        self.bot = bot
        self.dblpy = dbl.DBLClient(self.bot, self.bot._top)
        self.update_stats.start()

    @commands.Cog.listener()
    async def on_guild_post(self):
        print("x")
        
def setup(bot):
    bot.add_cog(DBLCog(bot))
