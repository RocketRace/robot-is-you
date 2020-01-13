import discord
import numpy     as np
import re

from datetime    import datetime
from discord.ext import commands
from inspect     import Parameter
from itertools   import chain
from io          import BytesIO
from json        import load
from os          import listdir
from os.path     import isfile
from PIL         import Image
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
            renderFrame = renderFrame.resize((2 * totalWidth, 2 * totalHeight))
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

    # Searches for a tile that matches the string provided
    @commands.command()
    @commands.cooldown(2, 10, type=commands.BucketType.channel)
    async def search(self, ctx, *, query: str):
        """
        Searches for tiles based on a query.

        **You may use these flags to navigate the output:**
        * `page`: Which page of output you wish to view. (Example usage: `search text page:2`)
        * `sort`: Which value to sort by. Defaults to `name`.
        * `reverse`: Whether or not the output should be in descending order or not. This may be `true` or `false`.

        **Queries may contain the following flags to filter results.**
        * `sprite`: The name of the sprite. Will return only tiles that use that sprite.
        * `text`: May be `true` or `false`. With `true`, this will only return text tiles.
        * `source`: The source of the sprite. Valid values for this are `vanilla`, `vanilla-extensions`, `cg5-mods`, `lily-and-patashu-mods`, `patasuhu-redux`, `misc`, and `modded`. Using `modded` will return any non-vanilla tiles.
        * `color`: The color index of the sprite. Must be two positive integers. Example: `1,2`
        * `tiling`: The tiling type of the object. This must be either `-1` (non-tiling objects), `0` (directional objects), `1` (tiling objects), `2` (character objects), `3` (directional & animated objects) or `4` (animated objects). 

        **Example commands:**
        `search baba`
        `search text:false source:vanilla sta`
        `search source:modded sort:color page:4`
        `search text:true color:0,3 reverse:true`
        """
        sanitizedQuery = discord.utils.escape_mentions(query)
        # Pattern to match flags in the format (flag):(value)
        flagPattern = r"([\d\w_]+):([\d\w,-_]+)"
        match = re.search(flagPattern, query)
        plainQuery = ""

        # Whether or not to use simple string matching
        hasFlags = bool(match)
        
        # Determine which flags to filter with
        flags = {}
        if hasFlags:
            if match:
                flags = dict(re.findall(flagPattern, query)) # Returns "flag":"value" pairs
            # Nasty regex to match words that are not flags
            nonFlagPattern = r"(?<![:\w\d,-])([\w\d,_]+)(?![:\d\w,-])"
            plainMatch = re.findall(nonFlagPattern, query)
            plainQuery = " ".join(plainMatch)
        
        # Which value to sort output by
        sortBy = "name"
        secondarySortBy = "name" # This is constant
        if flags.get("sort") is not None:
            sortBy = flags["sort"]
            flags.pop("sort")
        
        reverse = False
        reverseFlag = flags.get("reverse")
        if reverseFlag is not None and reverseFlag.lower() == "true":
            reverse = True
            flags.pop("reverse")

        page = 0
        pageFlag = flags.get("page")
        if pageFlag is not None and pageFlag.isnumeric():
            page = int(flags["page"]) - 1
            flags.pop("page")

        # How many results will be shown
        limit = 20
        results = 0
        matches = []

       # Searches through a list of the names of each tile
        data = self.bot.get_cog("Admin").tileColors
        for name,tile in data.items():
            if hasFlags:
                # Checks if the object matches all the flag parameters
                passed = {f:False for f,v in flags.items()}
                # Process flags for one object
                for flag,value in flags.items():
                    # Object name starts with "text_"
                    if flag.lower() == "text":
                        
                        if value.lower() == "true":
                            if name.startswith("text_"): passed[flag] = True

                        elif value.lower() == "false":
                            if not name.startswith("text_"): passed[flag] = True
                    
                    # Object source is vanilla, modded or (specific mod)
                    elif flag == "source":
                        if value.lower() == "modded":
                            if tile["source"] not in ["vanilla", "vanilla-extensions"]:
                                passed[flag] = True
                        else:
                            if tile["source"] == value.lower():
                                passed[flag] = True

                    # Object uses a specific color index ("x,y" is parsed to ["x", "y"])
                    elif flag == "color":
                        index = value.lower().split(",")
                        if tile["color"] == index:
                            passed[flag] = True

                    # For all other flags: Check that the specified object attribute has a certain value
                    else:  
                        if tile.get(flag) == value.lower():
                            passed[flag] = True
                
                # If we pass all flags (and there are more than 0 passed flags)
                if hasFlags and all(passed.values()):
                    if plainQuery in name:
                        results += 1
                        # Add our object to our results, and append its name (originally a key)
                        obj = tile
                        obj["name"] = name
                        matches.append(obj)

            # If we have no flags, simply use a substring search
            else:
                if query in name:
                    results += 1
                    obj = tile
                    obj["name"] = name
                    matches.append(obj)

        # Determine our output pagination
        firstResult = page * limit
        lastResult = (page + 1) * limit
        # Some sanitization to avoid negative indices
        if firstResult < 0: 
            firstResult = 0
        if lastResult < 0:
            lastResult = limit
        # If we try to go over the limit, just show the last page
        lastPage = results // limit
        if firstResult > results:
            firstResult = lastPage
        if lastResult > results:
            lastResult = results - 1
        
        # What message to prefix our output with
        if results == 0:
            matches.insert(0, f"Found no results for \"{sanitizedQuery}\".")
        elif results > limit:
            matches.insert(0, f"Found {results} results using query \"{sanitizedQuery}\". Showing page {page + 1} of {lastPage + 1}:")
        else:
            matches.insert(0, f"Found {results} results using query \"{sanitizedQuery}\":")
        
        # Tidy up our output with this mess
        content = "\n".join([f"**{x.get('name')}** : {', '.join([f'{k}: `{v[0]},{v[1]}`' if isinstance(v, list) else f'{k}: `{v}`' for k, v in sorted(x.items(), key=lambda λ: λ[0]) if k != 'name'])}" if not isinstance(x, str) else x for x in [matches[0]] + sorted(matches[1:], key=lambda λ: (λ[sortBy], λ[secondarySortBy]), reverse=reverse)[firstResult:lastResult + 1]])
        await self.bot.send(ctx, content)

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
        msg = []
        for palette in listdir("palettes"):
            if not palette in [".DS_Store"]:
                msg.append(palette[:-4])
        msg.sort()
        msg.insert(0, "Valid palettes:")
        await self.bot.send(ctx, "\n".join(msg))

    

    @commands.cooldown(2,10,type=commands.BucketType.channel)
    @commands.command(name="variants")
    async def listVariants(self, ctx, tile):
        '''
        List valid sprite variants for a given tile.
        '''
        # Clean the input
        cleanTile = tile.strip().lower()

        # Does the tile exist?
        data = self.bot.get_cog("Admin").tileColors.get(cleanTile)
        if data is None:
            return await self.bot.error(ctx, f"Could not find a tile with name '{cleanTile}'.")
        
        # Determines the tiling type of the tile
        tiling = data.get("tiling")

        # Possible tiling types and the corresponding available variants
        output = {
            None: [
                "This tile does not exist, or has no tiling data."
            ],
            "-1": [
                "This tile has no extra variants. It supports:",
                "`(no variant)` / `:0` / `:right` / `:r`"
            ],
            "0": [
                "This is a directional tile. It supports:",
                "`(no variant)` / `:0` / `:right` / `:r`",
                "`:8` / `:down` / `:d`",
                "`:16` / `:left` / `:l`",
                "`:24` / `:up` / `:u`"
            ],
            "1": [
                "This is a tiling tile. It automatically applies sprite variants to itself.",
            ],
            "2": [
                "This is a character tile. It supports directional and animated sprites, as well as sleeping sprites:",
                "`(no variant)` / `:0` / `:right` / `:r`",
                "`:1`",
                "`:2`",
                "`:3`",
                "`:7` / `:ds`",
                "`:8` / `:down` / `:d`",
                "`:9`",
                "`:10`",
                "`:11`",
                "`:15` / `:dl`",
                "`:16` / `:left` / `:l`",
                "`:17`",
                "`:18`",
                "`:19`",
                "`:23` / `:du`",
                "`:24` / `:up` / `:u`",
                "`:25`",
                "`:26`",
                "`:27`",
                "`:31` / `:sleep` / `rs`",
            ],
            "3": [
                "This is an animated & directional tile. It supports:",
                "`(no variant)` / `:0` / `:right` / `:r`",
                "`:1`",
                "`:2`",
                "`:3`",
                "`:8` / `:down` / `:d`",
                "`:9`",
                "`:10`",
                "`:11`",
                "`:16` / `:left` / `:l`",
                "`:17`",
                "`:18`",
                "`:19`",
                "`:24` / `:up` / `:u`",
                "`:25`",
                "`:26`",
                "`:27`"
            ],
            "4": [
                "This is an animated tile. It supports:",
                "`(no variant)` / `:0` / `:right` / `:r`",
                "`:1`",
                "`:2`",
                "`:3`"
            ]
        }

        # Output
        await self.bot.send(ctx, f"Valid sprite variants for '{cleanTile}'\n" + "\n".join(output[tiling]) + "\n")

    # Generates an animated gif of the tiles provided, using the default palette
    @commands.command(aliases=["rule"])
    @commands.cooldown(4, 10, type=commands.BucketType.channel)
    async def tile(self, ctx, *, objects: str = ""):
        """
        Renders the tiles provided.

        **Features:**
        * `palette` flag : Use this flag to recolor the output gif with the specified color palette. Use this in the format `palette:palette_name`. (See the `palettes` command for valid palettes.)
        * `background` flag: Use this flag to toggle background color. To enable, use `background:True`. By default, this is False.  
        * `rule` alias: Invoking the command with `rule` instead of `tile` will replace every tile with their text variants. Otherwise, render the text version of tiles with `text_object`.
        * `:variant` sprite variants: You may render a variant of a sprite by suffixing `:variant` to a tile. Valid variants for tiles are detailed in the `variants` command.

        **Special syntax:**
        * `-` : Renders an empty tile. 
        * `&` : Separate tiles with this to stack them on top of each other.
        * `,` : Input of the format `text_x,y...` or `tile_x,y,...` will be expanded into `text_x text_y ...` or `tile_x tile_y ...`
        * `||` : If you hide any of the input with spoiler tags, the output gif is marked as a spoiler.
        * `text_` : If this command is invoked using `tile`, you may render text tiles using `text_object`.
        * `tile_` : If this command is invoked using `rule`, you may render non-text tiles using `tile_object`.
        
        **Example commands:**
        `tile baba - keke`
        `tile palette:marshmallow keke:down baba:sleep`
        `rule rock is push`
        `rule tile_baba on baba is word`
        `tile text_baba,is,you`
        `tile baba&flag ||cake||`
        """
        async with ctx.typing():
            renderLimit = 64
            tiles = objects.lower().strip()
            if tiles == "":
                param = Parameter("objects", Parameter.KEYWORD_ONLY)
                raise commands.MissingRequiredArgument(param)

            # Determines if this should be a spoiler
            spoiler = tiles.replace("|", "") != tiles
            tiles = tiles.replace("|", "")

            # Determines if the command should use text tiles.
            rule = ctx.invoked_with == "rule"

            # check flags
            bgFlags = re.findall(r"background:true", tiles)
            background = None
            if bgFlags: background = (0,4)
            pattern = r"palette:\w+"
            paletteFlags = re.findall(pattern, tiles)
            palette = "default"
            for pal in paletteFlags:
                palette = pal[8:]
            if palette + ".png" not in listdir("palettes"):
                return await self.bot.error(ctx, f"Could not find a palette with name \"{pal}\".")

            tiles = "".join(re.split(pattern, tiles))
            tiles = tiles.replace("background:true", "")
            tiles = " ".join(re.split(" +", tiles))

            # Split input into lines
            wordRows = tiles.splitlines()
            
            # Split each row into words
            wordGrid = [row.split() for row in wordRows]

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
                                    # return await self.bot.send(ctx, f"⚠️ The sprite variant \"{variant}\"for \"{tile}\" doesn't seem to be valid.")
                                    # Replace bad variants with the default sprite 
                                    stack[i] = "default:0" 
                                    break
                                # Does a text counterpart exist?
                                suggestion = "text_" + tile
                                if isfile(f"color/{palette}/{suggestion}-{variant}-0-.png"):
                                    return await self.bot.error(ctx, f"Could not find a tile for \"{x}\".", f"Did you mean \"{suggestion}\"?")
                                # Did the user accidentally prepend "text_" via hand or using +rule?
                                suggestion = tile[5:]
                                if isfile(f"color/{palette}/{suggestion}-{variant}-0-.png"):
                                    # Under the `rule` command
                                    if rule:
                                        return await self.bot.error(ctx, f"Could not find a tile for \"{suggestion}\" under \"rule\".", f"Did you mean \"tile_{suggestion}\"?")
                                    # Under the `tile` command
                                    else:
                                        return await self.bot.error(ctx, f"Could not find a tile for \"{x}\".", f"Did you mean \"{suggestion}\"?")
                                # Answer to both of those: No
                                return await self.bot.error(ctx, f"Could not find a tile for \"{x}\".")

            # Merges the images found
            buffer = BytesIO()
            timestamp = datetime.now()
            formatString = "render_%Y-%m-%d_%H.%M.%S"
            formatted = timestamp.strftime(formatString)
            filename = f"{formatted}.gif"
            self.magickImages(wordGrid, width, height, palette=palette, background=background, out=buffer) # Previously used mergeImages()
        # Sends the image through discord
        await ctx.send(content=ctx.author.mention, file=discord.File(buffer, filename=filename, spoiler=spoiler))

    @commands.cooldown(2, 10, commands.BucketType.channel)
    @commands.command(name="level")
    async def _level(self, ctx, *, query):
        '''
        Renders the given Baba Is You level.
        Levels are searched for in the following order:
        * Checks if the input matches the level ID (e.g. "20level")
        * Checks if the input matches the level number (e.g. "space-3" or "lake-extra 1")
        * Checks if the input matches the level name (e.g. "further fields")
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
