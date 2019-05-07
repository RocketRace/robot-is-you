import discord
import numpy     as np

from discord.ext import commands
from json        import load
from PIL         import Image

def genFrame(fp):
    im = Image.open(fp)
    # Gets the alpha from the images
    alpha = im.getchannel("A")

    # Converts to 256 color, but only uses 255
    # Not sure if this acatually does anything
    im = im.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
    mask = Image.eval(alpha, lambda a: 255 if a == 0 else 0)

    # Gets the color value of the 0,0 pixel
    # This will be the transparency value in the .gif
    c = im.getpixel((0,0))

    # Pastes the transparency value to every spot on the picture that has alpha dictated by the mask above
    im.paste(c, mask)

    # Sets the transparency value to the pixel color
    im.info["transparency"] = c

    return im

def mergeImages(wordGrid, width, height):
    for f in range(3):
        pathGrid = [["empty.png" if word == "-" else "color/%s/%s-%s-.png" % ("default", word, f) for word in row] for row in wordGrid]
        frame = Image.new("RGBA", size=(48 * width, 48 * height))
        for i in range(height):
            for j in range(width):
                img = Image.open(pathGrid[i][j])
                frame.paste(img.resize((48,48)), (48 * j, 48 * i, 48 * j + 48, 48 * i + 48))
                frame.save("renders/frame%s.png" % f)
    f0 = genFrame("renders/frame0.png")
    f1 = genFrame("renders/frame1.png")
    f2 = genFrame("renders/frame2.png")
    f0.save("renders/render.gif", save_all=True, append_images=[f1, f2], duration=200, loop=0, disposal=2)

async def notTooManyArguments(ctx):
    return len(ctx.message.content.split(" ")) <= 50

class globalCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Check if the bot is loading
    async def cog_check(self, ctx):
        return self.bot.get_cog("ownerCog").notLoading

    # Generates an animated gif of the tiles provided, using (TODO) the default palette
    @commands.command()
    @commands.guild_only()
    @commands.check(notTooManyArguments)
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
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
        # Merges the images found
        mergeImages(wordGrid, width, height)
        # Sends the image through discord
        await ctx.send(content=ctx.author.mention, file=discord.File("renders/render.gif"))

    # Same as +tile but only for word tiles
    @commands.command()
    @commands.guild_only()
    @commands.check(notTooManyArguments)
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def rule(self, ctx, *, content:str):
        # Split input into a grid
        wordRows = content.lower().splitlines()
        wordGrid = [[word if word == "-" else "text_" + word for word in row.split()] for row in wordRows]

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
        except Exception as e:
            print(e)
            await ctx.send("⚠️ Could not find a tile for \"%s\"." % failedWord)
        # Merges the images found
        mergeImages(wordGrid, width, height)
        # Sends the image through discord
        await ctx.send(content=ctx.author.mention, file=discord.File("renders/render.gif"))

    @commands.command()
    @commands.cooldown(2, 5, commands.BucketType.channel)
    async def about(self, ctx):
        content = "ROBOT - Bot for Discord.\nDeveloped by RocketRace#0798 (156021301654454272) using the discord.py library." + \
            "Guilds: %s" % (len(self.bot.guilds))
        aboutEmbed = discord.Embed(title="About", type="rich", coloud=0xffff, description=content)
        await ctx.send(" ", embed=aboutEmbed)

    @commands.command()
    @commands.cooldown(2,5, commands.BucketType.channel)
    async def help(self, ctx):
        content = "Commands:\n`+help` : Displays this.\n`+about` : Displays bot info.\n" + \
            "`+tile [tiles]` : Renders the input tiles. Text tiles must be prefixed with \"text_\"." + \
            "Use hyphens to render empty tiles.\n`+rule [words]` : Like `+tile`, but only takes" + \
            "word tiles as input. Words do not need to be prefixed by \"text_\". Use hyphens to render empty tiles."
        helpEmbed = discord.Embed(title = "Help", type="rich", colour=0xffff, description=content)
        await ctx.send(" ", embed=helpEmbed)

    @rule.error
    async def ruleError(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send("⚠️ Command on cooldown.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("⚠️ Please input less than 50 tiles [Empty tiles included]")
    
    @tile.error
    async def tileError(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send("⚠️ Command on cooldown.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("⚠️ Please input less than 50 tiles [Empty tiles included]")

    @help.error
    async def helpError(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send("⚠️ Command on cooldown.")

def setup(bot):
    bot.add_cog(globalCog(bot))

