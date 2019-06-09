import discord
import numpy     as np

from discord.ext import commands
from itertools   import chain
from json        import load
from PIL         import Image
from subprocess  import call

# Takes a list of tile names and generates a gif with the associated sprites
async def magickImages(wordGrid, width, height, spoiler):
    # For each animation frame
    for fr in range(3):


        # Efficiently converts the grid back into a list of words
        wordList = chain.from_iterable(wordGrid)
        # Gets the path of each image
        paths = ["empty.png" if word == "-" else "color/%s/%s-%s-.png" % ("default", word, fr) for word in wordList]
        # Merges the images with imagemagick
        cmd =["magick", "montage", "-geometry", "200%+0+0", "-background", "none",
        "-colors", "255", "-tile", "%sx%s" % (width, height)]
        cmd.extend(paths) 
        cmd.append("renders/render_%s.png" % fr)
        call(cmd)
    # Determines if the image should be a spoiler
    spoilerText = "SPOILER_" if spoiler else ""
    # Joins each frame into a .gif
    fp = open(f"renders/{spoilerText}render.gif", "w")
    fp.truncate(0)
    fp.close()
    call(["magick", "convert", "renders/*.png", "-scale", "200%", "-set", "delay", "20", 
        "-set", "dispose", "2", "renders/%srender.gif" % spoilerText])

# For the +tile command.
async def notTooManyArguments(ctx):
    if len(ctx.message.content.split(" ")) <= 50 or ctx.message.author.id == 156021301654454272:
        return True
    else:
        await ctx.send("Please input less than 50 tiles [Empty tiles included]")
        return False

class globalCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Check if the bot is loading
    async def cog_check(self, ctx):
        return self.bot.get_cog("ownerCog").notLoading

    @commands.command()
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def custom(self, ctx):
        msg = discord.Embed(title="Custom Tiles?", description="Want custom tiles added to the bot? " + \
            "DM @RocketRace#0798 about it! \nI can help you if you send me:\n * **The sprites you want added**, " + \
            "preferably in an archived file (without any color, and in 24x24)\n * **The color of the sprites**, " + \
            "an (x,y) coordinate on the default Baba color palette.\nFor examples of this, check the `values.lua` " + \
            "file in your Baba Is You local files!", color=0x00ffff)
        ctx.send(" ", embed=msg)


    @commands.group()
    @commands.check(notTooManyArguments)
    async def render(self, ctx, *, content:str):
        async with ctx.typing():
            pass

    # Searches for a tile that matches the string provided
    @commands.command()
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def search(self, ctx, *, query: str):
        matches = []
        # How many results will be shown
        limit = 20
        # For substrings
        cutoff = len(query)
        try:
            # Searches through a list of the names of each tile
            for name in [tile["name"] for tile in bot.get_cog("ownerCog").tileColors]:
                match = False
                # If the name starts with {query}, match succeeds
                if name[:cutoff] == query:
                    match = True
                # If the name starts with "text_{query}", match succeeds
                if name[:5] == "text_":
                    if name[5:cutoff + 5] == query:
                        match = True
                if match:
                    if len(matches) >= limit:
                        raise Exception
                    else:
                        matches.append(name)
        except:
            matches.insert(0, f"Found more than {limit} results, showing only first {limit}:")
        finally:
            content = "\n".join(matches)
            await ctx.send(content)

    # Generates an animated gif of the tiles provided, using (TODO) the default palette
    @commands.command(aliases=["rule"])
    @commands.check(notTooManyArguments)
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def tile(self, ctx, *, content: str):
        async with ctx.typing():
            # Determines if this should be a spoiler
            spoiler = content.replace("|", "") != content

            # Determines if the command should use text tiles.
            rule = ctx.invoked_with == "rule"

            # Split input into lines
            if spoiler:
                wordRows = content.replace("|", "").lower().splitlines()
            else:
                wordRows = content.lower().splitlines()
            
            # Split each row into words
            wordGrid = [row.split() for row in wordRows]
            if rule:
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
            safe = True
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
            # The error is caught and an error message is sent
            except:
                await ctx.send("⚠️ Could not find a tile for \"%s\"." % failedWord)
                safe = False
                raise commands.BadArgument()
            if safe:
                # Merges the images found
                await magickImages(wordGrid, width, height, spoiler) # Previously used mergeImages()
                # Sends the image through discord
                if spoiler:
                    await ctx.send(content=ctx.author.mention, file=discord.File("renders/SPOILER_render.gif"))
                else:
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
            "word tiles as input. Words do not need to be prefixed by \"text\\_\". Use hyphens to render empty tiles." 
        helpEmbed = discord.Embed(title = "Help", type="rich", colour=0x00ffff, description=content)
        await ctx.send(" ", embed=helpEmbed)

def setup(bot):
    bot.add_cog(globalCog(bot))

