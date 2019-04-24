import discord
from discord.ext import commands

class ownerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="eval")
    @commands.is_owner()
    async def eval(self, ctx, *, content: str):
        success = True
        result = ""
        try:
            result = eval(content)
        except Exception as e:
            result = e
            success = False
        if success:
            await ctx.send(f"```\n✅ Evaluated successfully:\n{result}\n```")
        else:
            await ctx.send(f"```\n🚫 An exception occurred:\n{result}\n```")

def setup(bot):
    bot.add_cog(ownerCog(bot))