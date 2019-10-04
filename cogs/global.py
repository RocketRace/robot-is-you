import discord
import numpy     as np

from discord.ext import commands
from itertools   import chain
from json        import load
from os          import listdir
from os.path     import isfile
from PIL         import Image
from random      import choice
from subprocess  import call

def flatten(items, seqtypes=(list, tuple)):
    for i, x in enumerate(items):
        while i < len(items) and isinstance(items[i], seqtypes):
            items[i:i+1] = items[i]
    return items

# Takes a list of tile names and generates a gif with the associated sprites
def magickImages(wordGrid, width, height, palette):
    frames = []
    if palette == "hide":
        renderFrame = Image.new("RGBA", (48 * width, 48 * height))
        for i in range(3):
            frames.append(renderFrame)
        frames[0].save("renders/render.gif", "GIF",
            save_all=True,
            append_images=frames[1:],
            loop=0,
            duration=200,
            disposal=2, # Frames don't overlap
            transparency=255,
            background=255,
            optimize=False # Important in order to keep the color palettes from being unpredictable
        )
        return
    # For each animation frame
    paths = [
        [
            [
                [
                    None if word == "-" else f"color/{palette}/{word.split(':')[0]}-{word.split(':')[1]}-{fr}-.png" for word in stack
                ] for stack in row
            ] for row in wordGrid
        ] for fr in range(3)
    ]
    # Minimize IO by only opening each image once
    uniquePaths = set(flatten(paths.copy()))
    uniquePaths.discard(None)
    uniqueImages = {path:Image.open(path) for path in uniquePaths}
    
    imgs = [
        [
            [
                [
                    None if fp is None else uniqueImages[fp] for fp in stack
                ] for stack in row
            ] for row in fr
        ] for fr in paths
    ]
    # Only the first frame sizes matter
    sizes = [
        [
            [
                None if image is None else (image.width, image.height) for image in stack
            ] for stack in row
        ] for row in imgs[0]
    ]
    # Calculates padding based on image sizes
    leftPad = 0
    rightPad = 0
    upPad = 0
    downPad = 0
    for y,row in enumerate(sizes):
        for x,stack in enumerate(row):
            for size in stack:
                if size is not None:
                    if y == 0:
                        diff = size[1] - 24
                        if diff > upPad:
                            upPad = diff
                    if y == len(sizes) - 1:
                        diff = size[1] - 24
                        if diff > downPad:
                            downPad = diff
                    if x == 0:
                        diff = size[0] - 24
                        if diff > leftPad:
                            leftPad = diff
                    if x == len(row) - 1:
                        diff = size[0] - 24
                        if diff > rightPad:
                            rightPad = diff
    for frame in imgs:
        # Get new image dimensions, with appropriate padding
        totalWidth = len(frame[0]) * 24 + leftPad + rightPad 
        totalHeight = len(frame) * 24 + upPad + downPad 

        # Montage image
        renderFrame = Image.new("RGBA", (totalWidth, totalHeight))

        # Pastes each image onto the image
        # For each row
        yOffset = upPad # For padding: the cursor for example doesn't render fully when alone
        for row in frame:
            # For each image
            xOffset = leftPad # Padding
            for stack in row:
                for tile in stack:
                    if tile is not None:
                        width = tile.width
                        height = tile.height
                        # For tiles that don't adhere to the 24x24 sprite size
                        offset = (xOffset + (24 - width) // 2, yOffset + (24 - height) // 2)

                        renderFrame.paste(tile, offset, tile)
                xOffset += 24
            yOffset += 24

        # Resizes to 200%
        renderFrame = renderFrame.resize((2 * totalWidth, 2 * totalHeight))
        # Saves the final image
        frames.append(renderFrame)

    frames[0].save("renders/render.gif", "GIF",
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=200,
        disposal=2, # Frames don't overlap
        transparency=255,
        background=255,
        optimize=False # Important in order to keep the color palettes from being unpredictable
    )


class GlobalCog(commands.Cog, name="Baba Is You"):
    def __init__(self, bot):
        self.bot = bot
        with open("tips.json") as tips:
            self.tips = load(tips)

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
        await self.bot.send(ctx, " ", embed=msg)

    # Searches for a tile that matches the string provided
    @commands.command()
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def search(self, ctx, *, query: str):
        """
        Searches tiles for rendering from a query.
        Returns a list of tile names that matche the query.
        Can return up to 10 tiles per search.
        Tiles may be used in the `tile` (and subsequently `rule`) commands.
        """
        sanitizedQuery = discord.utils.escape_mentions(query)
        matches = []
        # How many results will be shown
        limit = 30
        try:
            # Searches through a list of the names of each tile
            for name in self.bot.get_cog("Admin").tileColors:
                if query in name:
                    if len(matches) >= limit:
                        raise OverflowError
                    else:
                        matches.append(name)
        except OverflowError:
            matches.insert(0, f"Found more than {limit} results, showing only first {limit}:")
        else:
            count = len(matches)
            if count == 0:
                matches.insert(0, f"Found no results for \"{sanitizedQuery}\".")
            else:
                matches.insert(0, f"Found {len(matches)} results for \"{sanitizedQuery}\":")
        content = "\n".join(matches)
        await self.bot.send(ctx, content)
    
    @commands.command()
    @commands.cooldown(2, 5, type=commands.BucketType.channel)
    async def tip(self, ctx):
        '''
        Gives a random helpful tip regarding this bot's functionality.
        '''
        randomTip = choice(self.tips)
        await self.bot.send(ctx, f"Here's a tip:\n*{randomTip}*")

    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    @commands.command(name="list")
    async def listTiles(self, ctx):
        """
        Lists valid tiles for rendering.
        Returns all valid tiles in a text file.
        Tiles may be used in the `tile` (and subsequently `rule`) commands.
        """
        fp = discord.File("tilelist.txt")
        await ctx.send( "List of all valid tiles:", file=fp)

    @commands.cooldown(2,10,type=commands.BucketType.channel)
    @commands.command(name="palettes")
    async def listPalettes(self, ctx):
        """
        Lists palettes usable for rendering.
        Palettes can be used as arguments for the `tile` (and subsequently `rule`) commands.
        """
        msg = ["Valid palettes:"]
        for palette in listdir("palettes"):
            if not palette in [".DS_Store"]:
                msg.append(palette[:-4])
        await self.bot.send(ctx, "\n".join(msg))

    # Generates an animated gif of the tiles provided, using (TODO) the default palette
    @commands.command(aliases=["rule"])
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def tile(self, ctx, *, palette: str, content: str = ""):
        """
        Renders the tiles provided, with many options. `help tile` for more...
        Returns a grid of 24 x 24 animated pixel sprites associated with each input tile. Up to 64 tiles may be rendered per command.
        
        The optional `<palette>` argument will recolor the output based on the color data of the palette. 
        `<palette>` must be of the format `palette:palette_name`. Valid palette names can be seen using the `palettes` command.
        
        Use hyphens to render empty tiles.

        Invoking this command using `rule` instead of `tile` will cause the "text" counterparts of each tile to be rendered instead.
        Otherwise, all text tiles are rendered with the format `text_object`.
        
        Input of the format `text_x,y,z...` will be expanded into `text_x, text_y, text_z, ...`. This is a convenience measure when working with many text tiles.

        Up to three tiles may be rendered in the same spot, on top of each other. You may stack tiles by separating them with `&`.
        An example of such stacked tiles: `baba&flag&text_you`

        If any part of the command is hidden behind spoiler tags (like ||this||), the resulting gif will be marked as a spoiler. 

        You may render a variant of a sprite by appending a suffix to the tile name. Valid suffixes are based on the tiling type of the object.
        Examples: 
        `baba:3` - The fourth animation frame of a baba moving right
        `bug:8` - A bug facing up
        `keke:31` - A keke facing right, sleeping
        Shorthands:
        `object:direction (up / down / left / right)` - The object facing the specified direction, if available.
        `object:sleep` - The object in a sleeping animation (facing right), if available.
        """
        async with ctx.typing():
            # The parameters of this command are a lie to appease the help command: here's what actually happens            
            tiles = palette
            renderLimit = 64

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
                    return await self.bot.send(ctx, f"⚠️ Could not find a palette with name \"{pal}\".")
                wordGrid[0].pop(0)
                if not wordGrid[0]:
                    wordGrid[0].append("-")
            else:
                pal = "default"
            
            # Splits the "text_x,y,z..." shortcuts into "text_x", "text_y", ...
            def splitCommas(grid, prefix):
                for row in grid:
                    toAdd = []
                    for i, word in enumerate(row):
                        if "," in word:
                            if word.startswith(prefix):
                                each = word.split(",")
                                expanded = [each[0]]
                                expanded.extend([prefix + segment for segment in each[1:]])
                                toAdd.append((i, expanded))
                            else:
                                raise Exception(word)
                    for change in reversed(toAdd):
                        row[change[0]:change[0] + 1] = change[1]
                return grid
            try:
                if rule:
                    wordGrid = splitCommas(wordGrid, "tile_")
                else:
                    wordGrid = splitCommas(wordGrid, "text_")
            except Exception as e:
                sourceOfException = e.args[0]
                return await self.bot.send(ctx, f"⚠️ I'm afraid I couldn't parse the following input: \"{sourceOfException}\".")

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
                        return await self.bot.send(ctx, f"⚠️ Stack too high ({height}). You may only stack up to 3 tiles on one space.")

            # Prepends "text_" to words if invoked under the rule command
            if rule:
                wordGrid = [[[word if word == "-" else word[5:] if word.startswith("tile_") else "text_" + word for word in stack] for stack in row] for row in wordGrid]

            # Get the dimensions of the grid
            lengths = [len(row) for row in wordGrid]
            width = max(lengths)
            height = len(wordRows)

            # Don't proceed if the request is too large.
            # (It shouldn't be that long to begin with because of Discord's 2000 character limit)
            area = width * height
            if area > renderLimit and ctx.author.id != self.bot.owner_id:
                return await self.bot.send(ctx, f"⚠️ Too many tiles ({area}). You may only render up to {renderLimit} tiles at once, including empty tiles.")

            # Now that we have width and height, we can accurately render the "hide" palette entries :^)
            if pal == "hide":
                wordGrid = [[["-" for tile in stack] for stack in row] for row in wordGrid]

            # Pad the word rows from the end to fit the dimensions
            [row.extend([["-"]] * (width - len(row))) for row in wordGrid]
            # Finds the associated image sprite for each word in the input
            # Throws an exception which sends an error message if a word is not found.
            
            # Appends ":0" to sprites without specified variants, and sets (& overrides) the suffix for tiled objects
            cloneGrid = [[[word for word in stack] for stack in row] for row in wordGrid]
            for y, row in enumerate(cloneGrid):
                for x, stack in enumerate(row):
                    for z, word in enumerate(stack):
                        if word != "-":
                            tile = word
                            variant = "0"
                            if ":" in word:
                                segments = word.split(":")
                                tile = segments[0]
                                variant = segments[1]

                            # Shorthand
                            if variant == "right":
                                variant = "0"
                            elif variant == "up":
                                variant = "8"
                            elif variant == "left":
                                variant = "16"
                            elif variant == "down":
                                variant = "24"
                            elif variant == "sleep":
                                variant = "31"
                            
                            
                            # Is this a tiling object (e.g. wall, water)?
                            tileData = self.bot.get_cog("Admin").tileColors.get(tile)
                            if tileData is not None:
                                if tileData.get("tiling") is not None:
                                    if tileData["tiling"] == "1":

                                        #  The final variation stace of the tile
                                        variant = 0

                                        # Tiles that join together
                                        def doesTile(stack):
                                            tileable = ["level", tile]
                                            for t in tileable:
                                                if t in stack:
                                                    return True
                                            return False

                                        # Is there the same tile adjacent right?
                                        if x != width - 1:
                                            # The tiles right of this (with variants stripped)
                                            adjacentRight = [t.split(":")[0] for t in cloneGrid[y][x + 1]]
                                            if doesTile(adjacentRight):
                                                variant += 1

                                        # Is there the same tile adjacent above?
                                        if y != 0:
                                            adjacentUp = [t.split(":")[0] for t in cloneGrid[y - 1][x]]
                                            if doesTile(adjacentUp):
                                                variant += 2

                                        # Is there the same tile adjacent left?
                                        if x != 0:
                                            adjacentLeft = [t.split(":")[0] for t in cloneGrid[y][x - 1]]
                                            if doesTile(adjacentLeft):
                                                variant += 4

                                        # Is there the same tile adjacent below?
                                        if y != height - 1:
                                            adjacentDown = [t.split(":")[0] for t in cloneGrid[y + 1][x]]
                                            if doesTile(adjacentDown):
                                                variant += 8
                                        
                                        # Stringify
                                        variant = str(variant)

                            # Finally, append the variant to the grid
                            wordGrid[y][x][z] = tile + ":" + variant
            del cloneGrid

            # Each row
            for row in wordGrid:
                # Each stack
                for stack in row:
                    # Each word
                    for word in stack:
                        if word != "-":
                            tile = word
                            variant = "0"
                            if ":" in tile:
                                segments = word.split(":")
                                variant = segments[1]
                                tile = segments[0]
                            # Checks for the word by attempting to open
                            if not isfile(f"color/{pal}/{tile}-{variant}-0-.png"):
                                if variant == "0":
                                    x = tile
                                else:
                                    x = word
                                # Is the variant faulty?
                                if isfile(f"color/{pal}/{tile}-{0}-0-.png"):
                                    return await self.bot.send(ctx, f"⚠️ The sprite variant \"{variant}\"for \"{tile}\" doesn't seem to be valid.")
                                # Does a text counterpart exist?
                                suggestion = "text_" + tile
                                if isfile(f"color/{pal}/{suggestion}-{variant}-0-.png"):
                                    return await self.bot.send(ctx, f"⚠️ Could not find a tile for \"{x}\". Did you mean \"{suggestion}\"?")
                                # Did the user accidentally prepend "text_" via hand or using +rule?
                                suggestion = tile[5:]
                                if isfile(f"color/{pal}/{suggestion}-{variant}-0-.png"):
                                    return await self.bot.send(ctx, f"⚠️ Could not find a tile for \"{x}\". Did you mean \"{suggestion}\"?")
                                # Answer to both of those: No
                                return await self.bot.send(ctx, f"⚠️ Could not find a tile for \"{x}\".")     

            # Merges the images found
            magickImages(wordGrid, width, height, pal) # Previously used mergeImages()
        # Sends the image through discord
        await ctx.send(content=ctx.author.mention, file=discord.File("renders/render.gif", spoiler=spoiler))

def setup(bot):
    bot.add_cog(GlobalCog(bot))
