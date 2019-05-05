import discord
import imageio
import os
import numpy     as np
from PIL         import Image
from json        import load
from discord.ext import commands

emoteCache = {}

class globalCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Generates an animated gif of the tiles provided, using (TODO) the default palette
    @commands.command()
    @commands.guild_only()
    async def tile(self, ctx, *, content: str):
        # Split input into a grid
        wordRows = content.lower().splitlines()
        wordGrid = [row.split() for row in wordRows]

        # Get the dimensions of the grid
        lengths = [len(row) for row in wordGrid]
        width = max(lengths)
        height = len(wordRows)

        # Pad the word rows from the end to fit the dimensions
        [row.extend(["-"] * (width - len(row))) for row in wordGrid]

        # Finds the associated image sprite for each word in the input
        # Throws an exception which sends an error message if a word is not found.
        failedWord = ""
        try:
            # Each row
            for row in wordGrid:
                # Each word
                for word in row:
                    # Checks for the word by attempting to open
                    # If not present, trows an exception...
                    if word != "-":
                        failedWord = word
                        open("color/%s/%s-0-.png" % ("default", word))
        # ... which is caught and an error message is sent
        except:
            await ctx.send("⚠️ Could not find a tile for \"%s\"." % failedWord)
        for f in range(3):
            pathGrid = [["empty.png" if word == "-" else "color/%s/%s-%s-.png" % ("default", word, f) for word in row] for row in wordGrid]
            frame = Image.new("RGBA", size=(24 * width, 24 * height))
            for i in range(height):
                for j in range(width):
                    img = Image.open(pathGrid[i][j])
                    frame.paste(img, (24 * j, 24 * i, 24 * j + 24, 24 * i + 24))
            frame.save("render%s.png" % f)
        f0 = genFrame("render0.png")
        f1 = genFrame("render1.png")
        f2 = genFrame("render2.png")
        f0.save("render.gif", save_all=True, append_images=[f1, f2], duration=200, loop=0, disposal=2)
        await ctx.send(content=ctx.author.mention, file=discord.File("render.gif"))
        
def genFrame(fp):
    im = Image.open(fp)
    alpha = im.getchannel("A")

    im = im.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
    mask = Image.eval(alpha, lambda a: 255 if a == 0 else 0)

    c = im.getpixel((0,0))

    im.paste(c, mask)

    im.info["transparency"] = c

    return im

def setup(bot):
    bot.add_cog(globalCog(bot))

