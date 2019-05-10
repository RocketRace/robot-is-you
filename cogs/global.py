import discord
import numpy     as np

from discord.ext import commands
from json        import load
from PIL         import Image

def genFrame(fp, pixel):
    im = Image.open(fp).convert("RGBA")
    # Gets the alpha from the images
    alpha = im.getchannel("A")

    # Converts to 256 color, but only uses 255
    # Not sure if this acatually does anything
    im = im.convert("RGB").quantize(colors=255)
    mask = Image.eval(alpha, lambda a: 255 if a <= 128 else 0)

    # Gets the color value of the px,0 pixel
    # This will be the transparency value in the .gif
    c = im.getpixel((0,2 * pixel))

    # Pastes the transparency value to every spot on the picture that has alpha dictated by the mask above
    im.paste(c, mask)

    # Sets the transparency value to the pixel color
    im.info["transparency"] = c

    return im

def mergeImages(wordGrid, width, height, spoiler):
    for f in range(3):
        pathGrid = [["empty.png" if word == "-" else "color/%s/%s-%s-.png" % ("default", word, f) for word in row] for row in wordGrid]
        frame = Image.new("RGBA", size=(48 * width, 48 * height))
        for i in range(height):
            for j in range(width):
                img = Image.open(pathGrid[i][j])
                frame.paste(img.resize((48,48)), (48 * j, 48 * i, 48 * j + 48, 48 * i + 48))
                frame.save("renders/frame%s.png" % f)
    px = 0
    if wordGrid[0][0] == "belt":
        px = 4
    
    f0 = genFrame("renders/frame0.png", px)
    f1 = genFrame("renders/frame1.png", px)
    f2 = genFrame("renders/frame2.png", px)
    if spoiler:
        name = "renders/SPOILER_render.gif"
    else:
        name = "renders/render.gif"
    f0.save(name, format="GIF", save_all=True, append_images=[f1, f2], duration=200, loop=0, disposal=2)

# For +tile and +rule commands.
async def notTooManyArguments(ctx):
    if len(ctx.message.content.split(" ")) <= 50:
        return True
    await ctx.send("⚠️ Please input less than 50 tiles [Empty tiles included]")
    return False

class globalCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Check if the bot is loading
    async def cog_check(self, ctx):
        return self.bot.get_cog("ownerCog").notLoading

    # Generates an animated gif of the tiles provided, using (TODO) the default palette, and with a spoiler tag.
    @commands.command()
    @commands.guild_only()
    @commands.check(notTooManyArguments)
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def spoiler(self, ctx, *, content: str):
        # Split input into a grid
        wordRows = content.replace("|", "").lower().splitlines()
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
        mergeImages(wordGrid, width, height, True)
        # Sends the image through discord
        await ctx.send(content=ctx.author.mention, file=discord.File("renders/SPOILER_render.gif"))


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
        mergeImages(wordGrid, width, height, False)
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
        mergeImages(wordGrid, width, height, False)
        # Sends the image through discord
        await ctx.send(content=ctx.author.mention, file=discord.File("renders/render.gif"))

    @commands.command()
    @commands.cooldown(2, 5, commands.BucketType.channel)
    async def about(self, ctx):
        content = "ROBOT - Bot for Discord based on the indie game Baba Is You." + \
            "\nDeveloped by RocketRace#0798 (156021301654454272) using the discord.py library." + \
            "\n[Github repository](https://github.com/RocketRace/robot-is-you)" + \
            "\nGuilds: %s" % (len(self.bot.guilds))
        aboutEmbed = discord.Embed(title="About", type="rich", colour=0x00ffff, description=content)
        await ctx.send(" ", embed=aboutEmbed)

    @commands.command()
    @commands.cooldown(2,5, commands.BucketType.channel)
    async def help(self, ctx):
        content = "Commands:\n`+help` : Displays this.\n`+about` : Displays bot info.\n" + \
            "`+tile [tiles]` : Renders the input tiles. Text tiles must be prefixed with \"text\\_\"." + \
            "Use hyphens to render empty tiles.\n`+rule [words]` : Like `+tile`, but only takes" + \
            "word tiles as input. Words do not need to be prefixed by \"text\\_\". Use hyphens to render empty tiles." + \
            "\n`+spoiler [tiles]` : Renders the input tiles and sends the results as a spoilered gif. Can read content" + \
            "inside spoiler tags. "
        helpEmbed = discord.Embed(title = "Help", type="rich", colour=0x00ffff, description=content)
        await ctx.send(" ", embed=helpEmbed)

def setup(bot):
    bot.add_cog(globalCog(bot))

