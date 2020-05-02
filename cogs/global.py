import discord
import re

from datetime    import datetime
from discord.ext import commands
from functools   import partial
from inspect     import Parameter
from io          import BytesIO
from json        import load
from os          import listdir
from os.path     import isfile
from PIL         import Image
from random      import choices, random
from string      import ascii_lowercase

def flatten(items, seqtypes=(list, tuple)):
    '''
    Flattens nested iterables, of speficied types.
    Via https://stackoverflow.com/a/10824086
    '''
    for i, _ in enumerate(items):
        while i < len(items) and isinstance(items[i], seqtypes):
            items[i:i+1] = items[i]
    return items

def tryIndex(string, value):
    '''
    Returns the index of a substring within a string.
    Returns -1 if not found.
    '''
    index = -1
    try:
        index = string.index(value)
    except:
        pass
    return index

class SplittingException(BaseException):
    pass

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
                    raise SplittingException(word)
        for change in reversed(toAdd):
            row[change[0]:change[0] + 1] = change[1]
    return grid

class GlobalCog(commands.Cog, name="Baba Is You"):
    def __init__(self, bot):
        self.bot = bot

    # Check if the bot is loading
    async def cog_check(self, ctx):
        '''
        Only if the bot is not loading assets
        '''
        return not self.bot.loading

    def saveFrames(self, frames, fp):
        '''
        Saves a list of images as a gif to the specified file path.
        '''
        frames[0].save(fp, "GIF",
            save_all=True,
            append_images=frames[1:],
            loop=0,
            duration=200,
            disposal=2, # Frames don't overlap
            transparency=255,
            background=255,
            optimize=False # Important in order to keep the color palettes from being unpredictable
        )
        if not isinstance(fp, str): fp.seek(0)

    def magickImages(self, wordGrid, width, height, *, palette="default", images=None, imageSource="vanilla", out="renders/render.gif", background=None):
        '''
        Takes a list of tile names and generates a gif with the associated sprites.

        out is a file path or buffer. Renders will be saved there, otherwise to `renders/render.gif`.

        palette is the name of the color palette to refer to when rendering.

        images is a list of background image filenames. Each image is retrieved from `images/{imageSource}/image`.

        background is a palette index. If given, the image background color is set to that color, otherwise transparent. Background images overwrite this. 

        tileBorder sets whether or not tiles stick to the edges of the image.
        '''
        frames = []
        if palette == "hide":
            # Silly "hide" palette that returns a blank render
            renderFrame = Image.new("RGBA", (48 * width, 48 * height))
            for _ in range(3):
                frames.append(renderFrame)
            return self.saveFrames(frames, out)

        # For each animation frame
        paths = [
            [
                [
                    [
                        None if word == "-" 
                        # Random animation offset for each position on the grid
                        else f"color/{palette}/{word.split(':')[0]}-{word.split(':')[1]}-{(hash(x + y + z) + fr) % 3}-.png" 
                        for z, word in enumerate(stack)
                    ] for x, stack in enumerate(row)
                ] for y, row in enumerate(wordGrid)
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
        
        for i,frame in enumerate(imgs):
            # Get new image dimensions, with appropriate padding
            totalWidth = len(frame[0]) * 24 + leftPad + rightPad 
            totalHeight = len(frame) * 24 + upPad + downPad 

            # Montage image
            # bg images
            if bool(images) and imageSource is not None:
                renderFrame = Image.new("RGBA", (totalWidth, totalHeight))
                # for loop in case multiple background images are used (i.e. baba's world map)
                for image in images:
                    overlap = Image.open(f"images/{imageSource}/{image}_{i + 1}.png") # i + 1 because 1-indexed
                    mask = overlap.getchannel("A")
                    renderFrame.paste(overlap, mask=mask)
            # bg color
            elif background is not None:
                paletteImg = Image.open(f"palettes/{palette}.png").convert("RGBA") # ensure alpha channel exists, even if blank
                paletteColor = paletteImg.getpixel(background)
                renderFrame = Image.new("RGBA", (totalWidth, totalHeight), color=paletteColor)
            # neither
            else: 
                renderFrame = Image.new("RGBA", (totalWidth, totalHeight))

            # Pastes each image onto the frame
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
            renderFrame = renderFrame.resize((2 * totalWidth, 2 * totalHeight), resample=Image.NEAREST)
            # Saves the final image
            frames.append(renderFrame)

        self.saveFrames(frames, out)

    def handleVariants(self, grid, *, tileBorders=False):
        '''
        Appends variants to tiles in a grid.
        Example:
        [[["baba", "keke:left"], ["flag:0"]], [["wall:0"], ["wall"]]]
        -> [[["baba:0", "keke:16"], ["flag:0"]], [["wall:1"], ["wall:4"]]]
        Explanation:
        * No variant -> :0
        * Shortcut variant -> The associated variant
        * Given variant -> untouched
        * Anything for a tiling object (given or not) -> variants generated according to adjacent tiles. 
        If tileBorders is given, this also depends on whether the tile is adjacent to the edge of the image.
        '''

        width = len(grid[0])
        height = len(grid)

        cloneGrid = [[[word for word in stack] for stack in row] for row in grid]
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

                        # Shorthands for sprite variants
                        if variant in ["r", "right"]:
                            variant = "0"
                        elif variant in ["u", "up"]:
                            variant = "8"
                        elif variant in ["l", "left"]:
                            variant = "16"
                        elif variant in ["d", "down"]:
                            variant = "24"
                        # Sleep variants
                        elif variant in ["s", "rs", "sleep"]: 
                            variant = "31"
                        elif variant in ["us"]:
                            variant = "7"
                        elif variant in ["ls"]:
                            variant = "15"
                        elif variant in ["ds"]:
                            variant = "23"
                        
                        # Is this a tiling object (e.g. wall, water)?
                        tileData = self.bot.get_cog("Admin").tileColors.get(tile)
                        if tileData is not None:
                            if tileData.get("tiling") is not None:
                                if tileData["tiling"] == "1":

                                    #  The final variation stace of the tile
                                    variant = 0

                                    # Tiles that join together
                                    def doesTile(stack):
                                        for t in stack:
                                            if t == tile or t.startswith("level"):
                                                return True
                                        return False

                                    # Is there the same tile adjacent right?
                                    if x != width - 1:
                                        # The tiles right of this (with variants stripped)
                                        adjacentRight = [t.split(":")[0] for t in cloneGrid[y][x + 1]]
                                        if doesTile(adjacentRight):
                                            variant += 1
                                    if tileBorders:
                                        if x == width - 1:
                                            variant += 1

                                    # Is there the same tile adjacent above?
                                    if y != 0:
                                        adjacentUp = [t.split(":")[0] for t in cloneGrid[y - 1][x]]
                                        if doesTile(adjacentUp):
                                            variant += 2
                                    if tileBorders:
                                        if y == 0:
                                            variant += 2

                                    # Is there the same tile adjacent left?
                                    if x != 0:
                                        adjacentLeft = [t.split(":")[0] for t in cloneGrid[y][x - 1]]
                                        if doesTile(adjacentLeft):
                                            variant += 4
                                    if tileBorders:
                                        if x == 0:
                                            variant += 4

                                    # Is there the same tile adjacent below?
                                    if y != height - 1:
                                        adjacentDown = [t.split(":")[0] for t in cloneGrid[y + 1][x]]
                                        if doesTile(adjacentDown):
                                            variant += 8
                                    if tileBorders:
                                        if y == height - 1:
                                            variant += 8
                                    
                                    # Stringify
                                    variant = str(variant)

                        # Finally, append the variant to the grid
                        grid[y][x][z] = tile + ":" + variant
        return grid

    @commands.command(hidden=True)
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def custom(self, ctx):
        msg = discord.Embed(title="Custom Tiles?", description="Want custom tiles added to the bot? " + \
            "DM @RocketRace#0798 about it! \nI can help you if you send me:\n * **The sprites you want added**, " + \
            "preferably in an archived file (without any color, and in 24x24)\n * **The color of the sprites**, " + \
            "an (x,y) coordinate on the default Baba color palette.\nFor examples of this, check the `values.lua` " + \
            "file in your Baba Is You local files!", color=self.bot.embedColor)
        await self.bot.send(ctx, " ", embed=msg)

    # @commands.cooldown(2, 10, type=commands.BucketType.channel)
    @commands.command(name="random")
    @commands.is_owner()
    async def randomRule(self, ctx):
        '''
        Generates a random valid rule.

        This command is disabled.
        '''
        textTypes = self.bot.get_cog("Admin").texts
        subject = choices(textTypes["0"], k=1)[0][5:] # strip text_ prefix
        verb = choices(textTypes["1"], k=1)[0][5:]
        
        # conditional statement
        useConditional = random() <= 0.7
        if useConditional:
            condWord = choices(textTypes["7"], k=1)[0][5:]
            condTarget = choices(textTypes["0"], k=1)[0][5:]
            conditional = f"{condWord} {condTarget} "
        else: conditional = " "
        
        if verb == "is":
            target = choices(textTypes[choices(("0", "2"), k=1)])[0][5:]
        else:
            target = choices(textTypes["0"], k=1)[0][5:]
        await self.bot.send(ctx, f"{subject} {conditional}{verb} {target}")

    async def renderTiles(self, ctx, *, objects, rule):
        '''
        Performs the bulk work for both `tile` and `rule` commands.
        '''
        async with ctx.typing():
            renderLimit = 64
            tiles = objects.lower().strip()
            if tiles == "":
                param = Parameter("objects", Parameter.KEYWORD_ONLY)
                raise commands.MissingRequiredArgument(param)

            # Determines if this should be a spoiler
            spoiler = tiles.replace("|", "") != tiles
            tiles = tiles.replace("|", "")

            # check flags
            bgFlags = re.findall(r"--background|-b", tiles)
            background = None
            if bgFlags: background = (0,4)
            pattern = r"--palette=\w+|-p=\w+"
            paletteFlags = re.findall(pattern, tiles)
            palette = "default"
            for pal in paletteFlags:
                palette = pal[pal.index("=") + 1:]
            if palette + ".png" not in listdir("palettes"):
                return await self.bot.error(ctx, f"Could not find a palette with name \"{pal}\".")

            tiles = "".join(re.split(pattern, tiles))
            tiles = tiles.replace("--background", "").replace("-b", "")
            tiles = " ".join(re.split(" +", tiles))

            # Check for empty input
            if not tiles:
                return await self.bot.error(ctx, "Input cannot be blank.")

            # Split input into lines
            wordRows = tiles.splitlines()
            
            # Split each row into words
            wordGrid = [row.split() for row in wordRows]

            try:
                if rule:
                    wordGrid = splitCommas(wordGrid, "tile_")
                else:
                    wordGrid = splitCommas(wordGrid, "text_")
            except SplittingException as e:
                sourceOfException = e.args[0]
                return await self.bot.error(ctx, f"I couldn't parse the following input: \"{sourceOfException}\".")

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
                        return await self.bot.error(ctx, f"Stack too high ({height}).", "You may only stack up to 3 tiles on one space.")

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
                return await self.bot.error(ctx, f"Too many tiles ({area}).", f"You may only render up to {renderLimit} tiles at once, including empty tiles.")

            # Now that we have width and height, we can accurately render the "hide" palette entries :^)
            if palette == "hide":
                wordGrid = [[["-" for tile in stack] for stack in row] for row in wordGrid]

            # Pad the word rows from the end to fit the dimensions
            [row.extend([["-"]] * (width - len(row))) for row in wordGrid]
            # Finds the associated image sprite for each word in the input
            # Throws an exception which sends an error message if a word is not found.
            
            # Appends ":0" to sprites without specified variants, and sets (& overrides) the suffix for tiled objects
            wordGrid = self.handleVariants(wordGrid)

            # Each row
            for row in wordGrid:
                # Each stack
                for stack in row:
                    # Each word
                    for i, word in enumerate(stack): 
                        if word != "-":
                            tile = word
                            variant = "0"
                            if ":" in tile:
                                segments = word.split(":")
                                variant = segments[1]
                                tile = segments[0]
                            # Checks for the word by attempting to open
                            if not isfile(f"color/{palette}/{tile}-{variant}-0-.png"):
                                if variant == "0":
                                    x = tile
                                else:
                                    x = word
                                # Is the variant faulty?
                                if isfile(f"color/{palette}/{tile}-{0}-0-.png"):
                                    if re.match(
                                        # voodoo magic regex to match valid variants
                                        r"r(ight|s)?|l(eft|s)?|d(own|s)?|u(p|s)?|s(leep)?|31|2[2-7]|1([0-1]|[5-9])|[7-9]|[0-3]",
                                        variant):
                                        stack[i] = "default:0"
                                        continue
                                    # not a real variant at all
                                    else:
                                        return await self.bot.error(ctx, f"⚠️ The sprite variant \"{variant}\" does not exist.")
                                # Does a text counterpart exist?
                                suggestion = "text_" + tile
                                if isfile(f"color/{palette}/{suggestion}-{variant}-0-.png"):
                                    return await self.bot.error(ctx, 
                                    f"Could not find a tile for \"{x}\".", 
                                    f"Did you mean \"{suggestion}\", or mean to use the `{ctx.prefix}rule` command?"
                                )
                                # Did the user accidentally prepend "text_" via hand or using +rule?
                                suggestion = tile[5:]
                                if isfile(f"color/{palette}/{suggestion}-{variant}-0-.png"):
                                    # Under the `rule` command
                                    if rule:
                                        return await self.bot.error(ctx, 
                                        f"Could not find a tile for \"{suggestion}\" under \"rule\".", 
                                        f"Did you mean \"tile_{suggestion}\", or mean to use the `{ctx.prefix}tile` command?"
                                    )
                                    # Under the `tile` command
                                    else:
                                        return await self.bot.error(ctx, 
                                        f"Could not find a tile for \"{x}\".", 
                                        f"Did you mean \"{suggestion}\"?"
                                    )
                                # tried to use old palette / background syntax?
                                if tile == "palette":
                                    return await self.bot.error(ctx, 
                                        f"Could not find a tile for \"{x}\".", 
                                        f"Did you mean to use the `--palette={variant}` or `-P={variant}` flag?"
                                    )
                                if tile == "background":
                                    return await self.bot.error(ctx, 
                                        f"Could not find a tile for \"{x}\".", 
                                        f"Did you mean to use the `--baclground` or `-B` flag?"
                                    )
                                return await self.bot.error(ctx, f"Could not find a tile for \"{x}\".")

            # Merges the images found
            buffer = BytesIO()
            timestamp = datetime.now()
            formatString = "render_%Y-%m-%d_%H.%M.%S"
            formatted = timestamp.strftime(formatString)
            filename = f"{formatted}.gif"
            task = partial(self.magickImages, wordGrid, width, height, palette=palette, background=background, out=buffer)
            await self.bot.loop.run_in_executor(None, task)
        # Sends the image through discord
        await ctx.send(content=ctx.author.mention, file=discord.File(buffer, filename=filename, spoiler=spoiler))
        

    @commands.command()
    @commands.cooldown(5, 10, type=commands.BucketType.channel)
    async def rule(self, ctx, *, objects = ""):
        '''
        Renders the text tiles provided.

        **Features:**
        * `--palette=<palette>` (`-P=<palette>`) flag: Recolors the output gif. (Example: `--palette=abstract`) See the `palettes` command for all valid palettes.
        * `--background` (`-B`) flag: Enables background color. Color is based on the active palette.
        * `:variant` sprite variants: Append `:variant` to a tile to render variants. See the `variants` command for more information.

        **Special syntax:**
        * `-` : Renders an empty tile. 
        * `&` : Stacks tiles on top of each other.
        * `tile_` : `tile_object` renders regular objects.
        * `,` : `tile_x,y,...` is expanded into `tile_x tile_y ...`
        * `||` : Marks the output gif as a spoiler. 
        
        **Example commands:**
        `rule baba is you`
        `rule -B rock is ||push||`
        `rule -P=test tile_baba on baba is word`
        `rule baba eat baba - tile_baba tile_baba:l`
        '''
        await self.renderTiles(ctx, objects=objects, rule=True)

    # Generates an animated gif of the tiles provided, using the default palette
    @commands.command()
    @commands.cooldown(5, 10, type=commands.BucketType.channel)
    async def tile(self, ctx, *, objects = ""):
        '''
        Renders the tiles provided.

        **Features:**
        * `--palette=<palette>` (`-P=<palette>`) flag: Recolors the output gif. (Example: `--palette=abstract`) See the `palettes` command for all valid palettes.
        * `--background` (`-B`) flag: Enables background color. Color is based on the active palette.
        * `:variant` sprite variants: Append `:variant` to a tile to render variants. See the `variants` command for more information.

        **Special syntax:**
        * `-` : Renders an empty tile. 
        * `&` : Stacks tiles on top of each other.
        * `text_` : `text_object` renders text objects.
        * `,` : `text_x,y,...` is expanded into `text_x text_y...`
        * `||` : Marks the output gif as a spoiler. 
        
        **Example commands:**
        `tile baba - keke`
        `tile --palette=marshmallow keke:d baba:s`
        `tile text_baba,is,you`
        `tile baba&flag ||cake||`
        `tile -P=mountain -B baba bird:l`
        '''
        await self.renderTiles(ctx, objects=objects, rule=False)

    @commands.cooldown(5, 10, commands.BucketType.channel)
    @commands.command(name="level")
    async def _level(self, ctx, *, query):
        '''
        Renders the given Baba Is You level.
        Levels are searched for in the following order:
        * Checks if the input matches the level ID (e.g. "20level")
        * Checks if the input matches the level number (e.g. "space-3" or "lake-extra 1")
        * Checks if the input matches the level name (e.g. "further fields")
        * Checks if the input is the ID of a world (e.g. "cavern")
        '''
        # User feedback
        await ctx.trigger_typing()

        levels = {}
        # Lower case, make the query all nice
        fineQuery = query.lower().strip()
        # Is it the level ID?
        levelData = self.bot.get_cog("Reader").levelData
        if levelData.get(fineQuery) is not None:
            levels[fineQuery] = levelData[fineQuery]

        # Does the query match a level tree?
        if len(levels) == 0:
            # Separates the map and the number / letter / extra number from the query.
            tree = [string.strip() for string in fineQuery.split("-")]
            # There should only be two parts to the query.
            if len(tree) == 2:
                # The two parts
                mapID = tree[0]
                identifier = tree[1]
                # What style of level identifier are we given?
                # Style: 0 -> "extra" + number
                # Style: 1 -> number
                # Style: 2 -> letter
                style = None
                # What "number" is the level?
                # .ld files use "number" to refer to both numbers, letters and extra numbers.
                number = None
                if identifier.isnumeric():
                    # Numbers
                    style = "0"
                    number = identifier
                elif len(identifier) == 1 and identifier.isalpha():
                    # Letters (only 1 letter)
                    style = "1"
                    # 0 <--> a
                    # 1 <--> b
                    # ...
                    # 25 <--> z
                    rawNumber = tryIndex(ascii_lowercase, identifier)
                    # If the identifier is a lowercase letter, set "number"
                    if rawNumber != -1: number = str(rawNumber)
                elif identifier.startswith("extra") and identifier[5:].strip().isnumeric():
                    # Extra numbers:
                    # Starting with "extra", ending with numbers
                    style = "2"
                    number = str(int(identifier[5:].strip()) - 1)
                else:
                    number = identifier
                    style = "-1"
                if style is not None and number is not None:
                    # Custom map ID?
                    if style == "-1":
                        # Check for the mapID & custom identifier combination
                        for filename,data in levelData.items():
                            if data["mapID"] == number and data["parent"] == mapID:
                                levels[filename] = data
                    else:
                        # Check for the mapID & identifier combination
                        for filename,data in levelData.items():
                            if data["style"] == style and data["number"] == number and data["parent"] == mapID:
                                levels[filename] = data

        # Is the query a real level name?
        if len(levels) == 0:
            for filename,data in levelData.items():
                # Matches an existing level name
                if data["name"] == fineQuery:
                    # Guaranteed
                    levels[filename] = data

        # MapID?
        if len(levels) == 0:
            for filename,data in levelData.items():
                if data["mapID"] == query and data["parent"] is None:
                    levels[filename] = data

        # If not found: error message
        if len(levels) == 0:
            return await self.bot.error(ctx, f'Could not find a level matching the query "{fineQuery}".')

        # If found:
        else:
            # Is there more than 1 match?
            matches = len(levels)

            # The first match
            data = list(levels.items())
            levelID = data[0][0]
            level = data[0][1]

            # The embedded file
            gif = discord.File(f"renders/{level['source']}/{levelID}.gif", spoiler=True)
            
            # Level name
            name = level["name"]

            # Level parent 
            parent = level.get("parent")
            mapID = level.get("mapID")
            tree = ""
            # Parse the display name
            if parent is not None:
                # With a custom mapID
                if mapID is not None:
                    # Format
                    tree = parent + "-" + mapID + ": "
                else:
                    # Parse the level style
                    style = level["style"]
                    number = level["number"]
                    identifier = None
                    # Regular numbers
                    if style == "0":
                        identifier = number
                    elif style == "1":
                    # Letters
                        identifier = ascii_lowercase[int(number)]
                    elif style == "2":
                    # Extra dots
                        identifier = "extra " + str(int(number) + 1)
                    else: 
                    # In case the custom mapID wasn't already set
                        identifier = mapID
                    # format
                    tree = parent + "-" + identifier + ": "
            
            # Level subtitle, if any
            subtitle = ""
            if level.get("subtitle") is not None:
                subtitle = "\nSubtitle: `" + level["subtitle"] + "`"

            # Any additional matches
            matchesText = "" if matches == 1 else f"\nFound {matches} matches: `{', '.join([l for l in levels])}`, showing the first." 

            # Formatted output
            formatted = f"{ctx.author.mention}{matchesText}\nName: `{tree}{name}`\nID: `{levelID}`{subtitle}"

            # Send the result
            await ctx.send(formatted, file=gif)

def setup(bot):
    bot.add_cog(GlobalCog(bot))
