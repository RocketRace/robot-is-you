# -*- coding: utf-8 -*-

from discord.ext import commands, tasks
import discord
import traceback
import aiohttp

class DBLCog(commands.Cog):
    '''
    Handle Top.gg guild count posting
    '''
    @tasks.loop(minutes=30)
    async def update_stats(self):
        url = f"https://top.gg/api/bots/{self.bot.user.id}/stats"
        headers = {"Authorization": self.bot._top}
        data = {"server_count": len(self.bot.guilds)}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data):
                pass
        

    @update_stats.before_loop
    async def prepare(self):
        await self.bot.wait_until_ready()

    def __init__(self, bot):
        self.bot = bot
        self.update_stats.start()

def setup(bot):
    bot.add_cog(DBLCog(bot))
