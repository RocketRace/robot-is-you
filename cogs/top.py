# -*- coding: utf-8 -*-

from discord.ext import commands
import discord
import dbl

class DBLCog(commands.Cog):
    '''
    Handle Top.gg guild count posting
    '''
    def __init__(self, bot):
        self.bot = bot
        try:
            self.dblpy = dbl.DBLClient(bot, bot._top, autopost=True)
        # Exception only raised in testing
        except dbl.UnauthorizedDetected:
            pass
        
def setup(bot):
    bot.add_cog(DBLCog(bot))
