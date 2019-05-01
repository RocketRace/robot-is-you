import discord
import imageio
import numpy as np
from discord.ext import commands
from os import listdir
from PIL import Image
from io import BytesIO

spriteColors = {}

def multiplyColor(fp, RGB):
    newR, newG, newB = RGB
    
    # Saves the alpha channel
    img = Image.open(fp).convert("RGBA")
    A = img.getchannel("A")

    # Multiplies the R,G,B channels with the input RGB values
    R,G,B = img.convert("RGB").split()
    R = R.point(lambda px: int(px * newR / 255))
    G = G.point(lambda px: int(px * newG / 255))
    B = B.point(lambda px: int(px * newB / 255))
    
    # Merges the channels and returns the RGBA image
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
        # Files within sprites/
        spriteNames = listdir("sprites") # Outputs are sadly not in order
        
        # Establishes the dict keys and fills them with Numpy arrays (for the associated texture files)
        for sprite in spriteNames:
            segments = sprite.split("_")

            # Only considers filenames that             
            if len(segments) >= 2:

                # Only considers the 0th sprite type for each text tile (there should only be a 0th type)
                if segments[-2] == "0":

                    # Joins the parts of the filename that form the object name
                    name = "_".join(segments[:-2])
                    
                    # Takes the last segment (e.g. "3.png") and saves one less than its first character's integer value.
                    animationFrame = segments.pop()[0]

                    # The corresponding sprite file
                    defaultImage = "sprites/" + sprite
                    
                    # Tests if the sprite has an associated color. 
                    # If true, changes the sprite color.
                    # If not, keeps the white sprite.
                    if spriteColors.get(name) == None:
                        image = Image.open(defaultImage)
                    else:
                        image = multiplyColor(defaultImage, spriteColors[name])
                    # Names are in the format "name_of_sprite-frame-.png" for further parsing
                    # This is different from the original format 
                    image.save("colored/" + name + "-" + animationFrame + "-.png", format="PNG")

        # Dict to put the ordered colored sprites in
        # Grouped according to tile name (=key)
        spriteFrames = {}

        # Newly created files within colored/
        coloredSprites = listdir("colored/")
        for sprite in coloredSprites:

            # Gets the necessary information from the filenames
            # Parses the aforementioned format like a piece of cake
            segments = sprite.split("-")
            name = segments[0]
            animationFrame = segments[1]
            if spriteFrames.get(name) == None:                
                # Puts in a dict because there's not necessarily 3 animation frames and the files are unordered
                # A list would probably be more efficient
                spriteFrames[name] = {}
            image = imageio.imread("colored/" + sprite, format="PNG")
            spriteFrames[name][animationFrame] = image

        # Loops over each set of animation frames and creates gifs from them.
        for name in spriteFrames:
            framesOrdered = []
            # Loops over each frame
            # These are sorted because of the string hashing? I think?
            for frame in spriteFrames[name]:
                framesOrdered.append(spriteFrames[name][frame])
            imageio.mimwrite("animated/" + name + ".gif", framesOrdered, format="GIF", fps=8)
            

     

def setup(bot):
    bot.add_cog(ownerCog(bot))