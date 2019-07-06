import discord
import numpy     as np

from discord.ext import commands
from itertools   import chain
from json        import load
from os          import listdir
from os.path     import isfile
from PIL         import Image
from subprocess  import call


# Custom exceptions

class InvalidTile(commands.UserInputError):
    pass

class TooManyTiles(commands.UserInputError):
    pass

class StackTooHigh(commands.UserInputError):
    pass

class InvalidPalette(commands.UserInputError):
    pass

# Takes a list of tile names and generates a gif with the associated sprites
async def magickImages(wordGrid, width, height, palette):
    # For each animation frame
    for fr in range(3):
        # Efficiently converts the grid back into a list of words
        # wordList = chain.from_iterable(wordGrid)
        # Opens each image
        paths = [[["empty.png" if word == "-" else "color/%s/%s-%s-.png" % (palette, word, fr) for word in stack] for stack in row] for row in wordGrid]
        imgs = [[[Image.open(fp) for fp in stack] for stack in row] for row in paths]

        # Get new image dimensions
        totalWidth = len(paths[0]) * 24
        totalHeight = len(paths) * 24

        # Montage image
        renderFrame = Image.new("RGBA", (totalWidth, totalHeight))

        # Pastes each image onto the image
        # For each row
        yOffset = 0
        for row in imgs:
            # For each image
            xOffset = 0
            for stack in row:
                for tile in stack:
                    renderFrame.paste(tile, (xOffset, yOffset), tile)
                xOffset += 24
            yOffset += 24

        # Saves the final image
        renderFrame.save(f"renders/{fr}.png")

    # Joins each frame into a .gif
    fp = open(f"renders/render.gif", "w")
    fp.truncate(0)
    fp.close()
    call(["magick", "convert", "renders/*.png", "-scale", "200%", "-set", "delay", "20", 
        "-set", "dispose", "2", "renders/render.gif"])


class GlobalCog(commands.Cog, name="Baba Is You"):
    def __init__(self, bot):
        self.bot = bot

    # Check if the bot is loading
    async def cog_check(self, ctx):
        return not self.bot.loading

    @commands.command(hidden=True)
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def custom(self, ctx):
        msg = discord.Embed(title="Custom Tiles?", description="Want custom tiles added to the bot? " + \
            "DM @RocketRace#0798 about it! \nI can help you if you send me:\n * **The sprites you want added**, " + \
            "preferably in an archived file (without any color, and in 24x24)\n * **The color of the sprites**, " + \
            "an (x,y) coordinate on the default Baba color palette.\nFor examples of this, check the `values.lua` " + \
            "file in your Baba Is You local files!", color=self.bot.embedColor)
        await ctx.send(" ", embed=msg)

    # Searches for a tile that matches the string provided
    @commands.command()
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def search(self, ctx, *, query: str):
        """
        Searches tiles for rendering from a query.
        Returns a list of tile names that matche the query.
        Can return up to 20 tiles per search.
        Tiles may be used in the `tile` (and subsequently `rule`) commands.
        """
        matches = []
        # How many results will be shown
        limit = 20
        # For substrings
        cutoff = len(query)
        try:
            # Searches through a list of the names of each tile
            for name in [tile["name"] for tile in self.bot.get_cog("Admin").tileColors]:
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
                        raise OverflowError
                    else:
                        matches.append(name)
        except OverflowError:
            matches.insert(0, f"Found more than {limit} results, showing only first {limit}:")
        else:
            count = len(matches)
            if count == 0:
                await ctx.send(f"Found no results for \"{query}\".")
            else:
                matches.insert(0, f"Found {len(matches)} results for \"{query}\":")
                content = "\n".join(matches)
                await ctx.send(content)

    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    @commands.command(name="list")
    async def listTiles(self, ctx):
        """
        Lists valid tiles for rendering.
        Returns all valid tiles in a text file.
        Tiles may be used in the `tile` (and subsequently `rule`) commands.
        """
        fp = discord.File("tilelist.txt")
        await ctx.send("List of all valid tiles:", file=fp)

    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    @commands.command()
    async def top(self, ctx, n: int = 20):
        """
        Returns the most commonly rendered tiles.
        If `n` is provided, returns up to 10 tiles, starting with the tile with rank `n` and counting down to rank `n - 10`.
        If `n` is 10 or less, returns the `n` most common tiles.
        """
        # Tidies up input
        if type(n) != int:
            raise TypeError
        if n < 1 or n > len(self.bot.tileStats) - 1:
            raise IndexError

        # Gets the values requested
        totals = {key:value for key, value in self.bot.tileStats.items() if key != "_total"}
        sortedKeys = sorted(totals, key=totals.get, reverse=True)
        if n <= 20:
            returnedKeys = sortedKeys[:n]
            returnCount = n
        else:
            returnedKeys = sortedKeys[(n - 20):n]
            returnCount = 20
        returnedValues = [totals[key] for key in returnedKeys]

        # Calculates the percentage the values are worth
        totalCount = totals.get("_total")
        percentages = [round(value / totalCount, 1) * 100 for value in returnedValues]

        # Makes it pretty
        neatPercentages = [str(pc) + " %" for pc in percentages]

        # Joins the data together into a nice list
        joined = [f"#{returnedKeys[i]}, `{returnedValues[i]}`: {neatPercentages[i]}" for i in range(returnCount)]

        # Joins the data into a string
        content = "\n".join(joined)
        content = "\n".join(f"The most commonly used tiles from #{n - returnCount + 1} to #{n}")
        embed = discord.Embed(title="Top Tiles", description=content, color=self.bot.embedColor)
        await ctx.send(" ", embed=embed)

    @commands.cooldown(2,10,type=commands.BucketType.channel)
    @commands.command(name="palettes")
    async def listPalettes(self, ctx):
        """
        Lists palettes usable for rendering.
        Palettes can be used as arguments for the `tile` (and subsequently `rule`) commands.
        """
        msg = ["Valid palettes:"]
        for palette in listdir("palettes"):
            msg.append(palette[:-4])
        await ctx.send("\n".join(msg))

    # Generates an animated gif of the tiles provided, using (TODO) the default palette
    @commands.command(aliases=["rule"])
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def tile(self, ctx, *, palette: str, content: str = ""):
        """
        Renders the tiles provided, with many options. `help tile` for more...
        Returns a grid of 24 x 24 animated pixel sprites associated with each input tile. Up to 50 tiles may be rendered per command.
        
        The optional `<palette>` argument will recolor the output based on the color data of the palette. 
        `<palette>` must be of the format `palette:palette_name`. Valid palette names can be seen using the `palettes` command.
        
        Use hyphens to render empty tiles.

        Invoking this command using `rule` instead of `tile` will cause the "text" counterparts of each tile to be rendered instead.
        Otherwise, all text tiles are rendered with the format `text_object`.
        
        Input of the format `text_x,y,z...` will be expanded into `text_x, text_y, text_z, ...`. This is a convenience measure when working with many text tiles.

        Up to three tiles may be rendered in the same spot, on top of each other. You may stack tiles by separating them with `&`.
        An example of such stacked tiles: `baba&flag&text_you`

        If any part of the command is hidden behind spoiler tags (like ||this||), the resulting gif will be marked as a spoiler. 
        """
        async with ctx.typing():
            # The parameters of this command are a lie to appease the help command: here's what actually happens            
            tiles = palette
            
            # Determines if this should be a spoiler
            spoiler = tiles.replace("|", "") != tiles

            # Determines if the command should use text tiles.
            rule = ctx.invoked_with == "rule"

            # Split input into lines
            if spoiler:
                wordRows = tiles.replace("|", "").lower().splitlines()
            else:
                wordRows = tiles.lower().splitlines()
            
            # Split each row into words
            wordGrid = [row.split() for row in wordRows]

            # Determines which palette to use
            # If the argument (i.e. the first tile) is of the format "palette:xyz", it is popped from the tile list
            firstarg = wordGrid[0][0]
            pal = ""
            if firstarg.startswith("palette:"):
                pal = firstarg[8:] 
                if pal + ".png" not in listdir("palettes"):
                    raise InvalidPalette(pal)
                wordGrid[0].pop(0)
                if not wordGrid[0]:
                    wordGrid[0].append("-")
            else:
                pal = "default"
            
            # Splits the "text_x,y,z..." shortcuts into "text_x", "text_y", ...
            if not rule:
                for row in wordGrid:
                    toAdd = []
                    for i, word in enumerate(row):
                        if "," in word:
                            each = word.split(",")
                            expanded = [each[0]]
                            expanded.extend(["text_" + segment for segment in each[1:]])
                            toAdd.append((i, expanded))
                    for change in reversed(toAdd):
                        row[change[0]:change[0] + 1] = change[1]

            # Splits "&"-joined words into stacks
            for row in wordGrid:
                for i,stack in enumerate(row):
                    if "&" in stack:
                        row[i] = stack.split("&")
                    else:
                        row[i] = [stack]
                    # Limit how many tiles can be rendered in one space
                    height = len(row[i])
                    if height > 3 and ctx.author.id != self.bot.owner_id:
                        raise StackTooHigh(str(height))

            # Prepends "text_" to words if invoked under the rule command
            if rule:
                wordGrid = [[[word if word == "-" else "text_" + word for word in stack] for stack in row] for row in wordGrid]

            # Get the dimensions of the grid
            lengths = [len(row) for row in wordGrid]
            width = max(lengths)
            height = len(wordRows)

            # Don't proceed if the request is too long.
            # (It shouldn't be that long to begin with because of Discord's 2000 character limit)
            area = width * height
            if area > 50 and ctx.author.id != self.bot.owner_id:
                raise TooManyTiles(str(area))

            # Pad the word rows from the end to fit the dimensions
            [row.extend([["-"]] * (width - len(row))) for row in wordGrid]
            # Finds the associated image sprite for each word in the input
            # Throws an exception which sends an error message if a word is not found.
            
            # Each row
            for row in wordGrid:
                # Each stack
                for stack in row:
                    # Each word
                    for word in stack:
                        # Checks for the word by attempting to open
                        # If not present, trows an exception.
                        if word != "-":
                            if not isfile(f"color/{pal}/{word}-0-.png"):
                                raise InvalidTile(word)
                
            # Gathers statistics on the tiles, now that the grid is "pure"
            for row in wordGrid:
                for stack in row:
                    for word in stack:
                        if self.bot.tileStats.get(word) is None:
                            self.bot.tileStats[word] = 1
                        else:
                            self.bot.tileStats[word] += 1
                        self.bot.tileStats["_total"] += 1               

            # Merges the images found
            await magickImages(wordGrid, width, height, pal) # Previously used mergeImages()
            # Sends the image through discord
            await ctx.send(content=ctx.author.mention, file=discord.File("renders/render.gif", spoiler=spoiler))

    @tile.error
    async def tileError(self, ctx, error):
        print(error)
        print(error.args)
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(error)
        elif isinstance(error, InvalidTile):
            word = error.args[0]
            await ctx.send(f"⚠️ Could not find a tile for \"{word}\".")
        elif isinstance(error, TooManyTiles):
            await ctx.send(f"⚠️ Too many tiles ({error.args[0]}). You may only render up to 50 tiles at once, including empty tiles.")
        elif isinstance(error, StackTooHigh):
            await ctx.send(f"⚠️ Stack too high ({error.args[0]}). You may only stack up to 3 tiles on one space.")
        elif isinstance(error, InvalidPalette):
            await ctx.send(f"⚠️ Could not find a palette with name {error.args[0]}).")

def setup(bot):
    bot.add_cog(GlobalCog(bot))
