import discord
import imageio
import numpy as np
from discord.ext import commands
from os import listdir
from PIL import Image
from io import BytesIO

def multiplyColor(fp, RGB):
    newR, newG, newB = RGB
    img = Image.open(fp).convert("RGBA")
    A = img.getchannel("A")

    R,G,B = img.convert("RGB").split()
    R = R.point(lambda px: int(px * newR / 255))
    G = G.point(lambda px: int(px * newG / 255))
    B = B.point(lambda px: int(px * newB / 255))
    RGBA = Image.merge("RGBA", (R, G, B, A))
    return RGBA
    
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

    @commands.command(name="reloadpalette")
    @commands.is_owner()
    async def reloadpalette(self, ctx, message):
        pass

    @commands.command(name="refillemotes",)
    @commands.is_owner()
    async def refillemotecache(self, ctx):
        objectFrames = {}
        spriteColors = {}
        spriteNames = listdir("sprites") # Outputs are sadly not in order
        # Establishes the dict keys and fills them with Numpy arrays (for the associated texture files)
        for sprite in spriteNames:
            segments = sprite.split("_")
            # Only considers the 0th sprite type for each text tile (there should only be a 0th type)
            if segments[-2] == "0":
                # Joins the parts of the filename that form the object name
                name = "_".join(segments[:-2])
                # Takes the last segment (e.g. "3.png") and saves one less than its first character's integer value.
                animationFrame = int(segments.pop()[0]) - 1

                # The corresponding sprite file
                defaultImage = open(sprite)
                
                # Tests if the sprite has an associated color. 
                # If true, changes the sprite color.
                # If not, keeps the white sprite.
                if spriteColors.get(name) == None:
                    image = defaultImage
                else:
                    image = multiplyColor(defaultImage, spriteColors[name])
                
                # Tests if the object dict has sprites already.
                # If true, adds the image to the list of sprites at its corresponding frame of animation.
                # If not, makes sure it does.
                if objectFrames.get(name) == None:
                    objectFrames[name] = [0,0,0]
                    objectFrames[name][animationFrame] = image
                else:
                    objectFrames[name][animationFrame] = image
                    

def setup(bot):
    bot.add_cog(ownerCog(bot))