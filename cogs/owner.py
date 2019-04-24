import discord
from discord.ext import commands
import imageio
import os
import numpy

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

    @commands.command(name="reloademotes",)
    @commands.is_owner()
    async def refillemotecache(self, ctx):
        objectFrames = {}
        spriteNames = os.listdir("sprites") # Outputs are sadly not in order
        # Establishes dictionary keys
        for sprite in spriteNames:
            segments = objectFrames[sprite.split("_")]
            if segments[0] == "text":
                image = imageio.imread("sprites/" + sprite, format="PNG")
                if objectFrames.get(segments[1]) == None:
                    objectFrames[segments[1]] = [image]
                else:
                    objectFrames[segments[1]].append(image)




def setup(bot):
    bot.add_cog(ownerCog(bot))