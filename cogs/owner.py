import ast
import asyncio
import discord
import json
import numpy      as np

from datetime     import datetime, timedelta
from discord.ext  import commands
from os           import listdir, stat
from pathlib      import Path
from PIL          import Image, ImageDraw, ImageChops

def multiplyColor(fp, palettes, pixels):
    # fp: file path of the sprite
    # palettes: each palette name
    # pixels: the colors the tile should be recolored with

    uniquePixels = {}
    for palette,pixel in zip(palettes, pixels):
        uniquePixels.setdefault(pixel, []).append(palette)
    
    # Output images
    recolored = []
    outputPalettes = uniquePixels.values()

    # Image to recolor from
    base = Image.open(fp).convert("RGBA")

    # Multiplies the R,G,B channel for each pixel value
    for pixel in uniquePixels:
        # New values
        newR, newG, newB = pixel
        # New channels
        arr = np.asarray(base, dtype='uint16')
        rC, gC, bC, aC = arr.T
        rC, gC, bC = newR*rC / 256, newG*gC / 256, newB*bC / 256
        out = np.stack((rC.T,gC.T,bC.T,aC.T),axis=2).astype('uint8')
        RGBA = Image.fromarray(out)
        # Adds to list
        recolored.append(RGBA)

    return zip(recolored, outputPalettes)

def getSpriteVariants(sprite, tiling):
    '''
    Opens the associated sprites from sprites/
    Use every sprite variant, the amount based on the tiling type

    Sprite variants follow this scheme:

    == IF NOT TILING TYPE 1 ==

    Change by 1 := Change in animation

    -> 0,1,2,3 := Regular animation

    -> 7 := Sleeping animation

    Change by 8 := Change in direction

    == IF TYLING TYPE 1 ==
    
    0  := None adjacent
    
    1  := Right
    
    2  := Up
    
    3  := Up & Right
    
    4  := Left
    
    5  := Left & Right
    
    6  := Left & Up
    
    7  := Left & Right & Up
    
    8  := Down
    
    9  := Down & Right
    
    10 := Down & Up
    
    11 := Down & Right & Up
    
    12 := Down & Left
    
    13 := Down & Left & Right
    
    14 := Down & Left & Up
    
    15 := Down & Left & Right & Up
    '''

    if tiling == "4": # Animated, non-directional
        spriteNumbers = [0,1,2,3] # Animation
    if tiling == "3" and sprite != "goose": # Basically for belts only (anim + dirs)
        spriteNumbers = [0,1,2,3, # Animation right
                        8,9,10,11, # Animation up
                        16,17,18,19, # Animation left
                        24,25,26,27] # Animation down

    if tiling == "3" and sprite == "goose": # For Goose (anim + dirs)
        spriteNumbers = [0,1,2,3, # Animation right
                        # Goose has no up animations ¯\_(ツ)_/¯
                        16,17,18,19, # Animation left
                        24,25,26,27] # Animation down

    elif tiling == "2" and sprite != "robot": # Baba, Keke, Me and Anni have some wonky sprite variations
        spriteNumbers = [0,1,2,3, # Moving animation to the right
                        7, # Sleep up
                        8,9,10, 11, # Moving animation up
                        15, # Sleep left
                        16,17,18,19, #Moving animation left
                        23, # Sleep down
                        24,25,26,27, # Moving animation down
                        31] # Sleep right

    elif tiling == "2" and sprite == "robot": 
        # Robot has no sleep animations but is a character ¯\_(ツ)_/¯
        spriteNumbers = [0,1,2,3, # Moving animation to the right
                        8,9,10, 11, # Moving animation up
                        16,17,18,19, #Moving animation left
                        24,25,26,27] # Moving animation down

    elif tiling == "1": # "Tiling" objects
        spriteNumbers = [i for i in range(16)]

    elif tiling == "0": # "Directional" objects have these sprite variations: 
        spriteNumbers = [0,8,16,24]

    else: # No tiling
        spriteNumbers = [0]
    
    return spriteNumbers
    
def load_with_datetime(pairs, format='%Y-%m-%dT%H:%M:%S.%f'):
    '''
    Load json + datetime objects, in the speficied format.
    Via https://stackoverflow.com/a/14996040
    '''
    d = {}
    for k, l in pairs:
        if isinstance(l, list):
            t = []
            for v in l:
                try:
                    x = datetime.strptime(v, format)
                except ValueError:
                    x = v
                finally:
                    t.append(x)
            d[k] = t
        else:
            d[k] = l             
    return d
    
class OwnerCog(commands.Cog, name="Admin", command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self.tileData = {}
        self.identifies = []
        self.resumes = []
        # Loads the caches
        # Loads the tile colors, if it exists
        colorsFile = "cache/tiledata.json"
        if stat(colorsFile).st_size != 0:
            self.tileData = json.load(open(colorsFile))
            
        # Loads the alternate tiles if possible
        # Loads debug data, if any
        debugFile = "cache/debug.json"
        if stat(debugFile).st_size != 0:
            debugData = json.load(open(debugFile), object_pairs_hook=load_with_datetime)
            self.identifies = debugData.get("identifies")
            self.resumes = debugData.get("resumes")

        self.initializeletters()
        
        # Are assets loading?
        self.bot.loading = False

    @commands.command()
    async def yoo(self, ctx):
        return 1 / 0

    def generateTileSprites(self, tile, obj, palettes, colors):
        # Fetches the tile data
        sprite = obj["sprite"]
        tiling = obj.get("tiling")
        # Custom tiles will probably not have the tiling property unless specified
        if tiling is None: tiling = "-1"
        color = obj["color"]
        source = obj.get("source")
        # If not specified, it's a vanilla sprite
        if source is None: source = "vanilla"
        # For convenience
        x,y = [int(n) for n in color]
        spriteVariants = getSpriteVariants(sprite, tiling)

        # Saves the tile sprites
        singleFrame = ["smiley", "hi", "plus"] # Filename is of the format "smiley_1.png"
        noVariants = ["default"] # Filenames are of the format "default_<1/2/3>.png"
        for variant in spriteVariants:
            if tile in singleFrame or tile.startswith("icon"): # Icons have a single frame
                if tile == "icon":
                    paths = [f"sprites/{source}/icon.png" for i in range(3)]
                else:
                    paths = [f"sprites/{source}/{sprite}_1.png" for i in range(3)]
            elif tile in noVariants:
                paths = [f"sprites/{source}/{sprite}_{i + 1}.png" for i in range(3)]
            else:
                # Paths should only be of length 3
                paths = [f"sprites/{source}/{sprite}_{variant}_{i + 1}.png" for i in range(3)]
            
            # Changes the color of each image, then saves it
            for i,fp in enumerate(paths):
                pixels = [img[x][y] for img in colors]
                recolored = multiplyColor(fp, palettes, pixels)
                # Saves the colored images to /color/[palette]/ given that the image may be identical for some palettes
                # Recolored images, palettes each image is associated with
                for img,uses in recolored:
                    # Each associated palette
                    for use in uses:
                        # This saves some redundant computing time spent recoloring the same image multiple times
                        # (up to >10 for certain color indices)
                        img.save(f"color/{use}/{tile}-{variant}-{i}-.png", format="PNG")
            
    @commands.command(aliases=["load", "reload"])
    @commands.is_owner()
    async def reloadcog(self, ctx, cog = None):
        '''
        Reloads extensions within the bot while the bot is running.
        '''
        if cog is None:
            extensions = [a for a in self.bot.extensions.keys()]
            for extension in extensions:
                self.bot.reload_extension(extension)
            await ctx.send("Reloaded all extensions.")
        elif "cogs." + cog in self.bot.extensions.keys():
            self.bot.reload_extension("cogs." + cog)
            await ctx.send(f"Reloaded extension `{cog}` from `cogs/{cog}.py`.")
        else:
            await ctx.send("Unknown extension provided.")

    @commands.command(aliases=["reboot"])
    @commands.is_owner()
    async def restart(self, ctx):
        '''
        Restarts the bot process.
        '''
        await ctx.send("Restarting bot process...")
        self.bot.exit_code = 1
        await self.bot.logout()

    @commands.command(aliases=["kill", "yeet"])
    @commands.is_owner()
    async def logout(self, ctx):
        '''
        Kills the bot process.
        '''
        if ctx.invoked_with == "yeet":
            await ctx.send("Yeeting bot process...")
        else:
            await ctx.send("Killing bot process...")
        await self.bot.logout()

    @commands.command()
    @commands.is_owner()
    async def debug(self, ctx):
        '''
        Gives some debug stats.
        '''
        yesterday = datetime.utcnow() - timedelta(days=1)
        identifiesDay = [event for event in self.identifies if event > yesterday]
        resumesDay = [event for event in self.resumes if event > yesterday]
        iCount = len(identifiesDay)
        rCount = len(resumesDay)

        globalRateLimit = not self.bot.http._global_over.is_set()

        msg = discord.Embed(
            title="Debug",
            description="".join([f"IDENTIFYs in the past 24 hours: {iCount}\n",
                f"RESUMEs in the past 24 hours: {rCount}\n",
                f"Global rate limit: {globalRateLimit}"]),
            color=self.bot.embedColor
        )

        await self.bot.send(ctx, " ", embed=msg)
        
    # Sends a message in the specified channel
    @commands.command()
    @commands.is_owner()
    async def announce(self, ctx, channel, title, *, content):
        t = title
        t = t.replace("_", " ")
        embed = discord.Embed(title=t, type="rich", description=content, colour=0x00ffff)
        await self.bot.send(ctx.message.channel_mentions[0], " ", embed=embed)

    @commands.command()
    @commands.is_owner()
    async def loadchanges(self, ctx):
        '''
        Scrapes alternate tile data from level metadata (`.ld`) files.
        '''
        self.bot.loading = True
        
        alternateTiles = {}

        levels = [l for l in listdir("levels/vanilla") if l.endswith(".ld")]
        for level in levels:
            # Reads each line of the level file
            lines = ""
            with open("levels/vanilla/%s" % level) as fp:
                lines = fp.readlines()

            IDs = []
            alts = {}

            # Loop through the lines
            for line in lines:
                # Only considers lines starting with objectXYZ
                if line.startswith("changed="):
                    if len(line) > 16:
                        IDs = [line[8:17]]
                        IDs.extend(line.strip().split(",")[1:-1])
                        alts = dict.fromkeys(IDs[:])
                        for alt in alts:
                            alts[alt] = {"name":"", "sprite":"", "tiling":"", "color":[], "type":""}
                else:
                    if line.startswith("object"):
                        ID = line[:][:9]
                        # If the line matches "objectZYX_name="
                        # Sets the changed name
                        if line[10:].startswith("name="):
                            # Magic numbers used to grab only the name of the sprite
                            # Same is used below for sprites/colors
                            name = line[:][15:-1]
                            alts[ID]["name"] = name
                        # Sets the changed sprite
                        elif line.startswith("image=", 10):
                            sprite = line[:][16:-1]
                            alts[ID]["sprite"] = sprite
                        # Tiling type
                        elif line.startswith("tiling=", 10):
                            alts[ID]["tiling"] = line[:][17:-1]
                        # Text type
                        elif line.startswith("type=", 10):
                            alts[ID]["type"] = line[:][15:-1]
                        # Sets the changed color (all tiles)
                        elif line.startswith("colour=", 10):
                            colorRaw = line[:][17:-1]
                            # Splits the color into a list 
                            # "a,b" -> [a,b]
                            color = colorRaw.split(",")
                            if not alts[ID].get("color"):
                                alts[ID]["color"] = color
                        # Sets the changed color (active text only), overrides previous
                        elif line.startswith("activecolour=", 10):
                            colorRaw = line[:][23:-1]
                            # Splits the color into a list 
                            # "a,b" -> [a,b]
                            color = colorRaw.split(",")
                            alts[ID]["color"] = color
                    
            # Adds the data to the list of changed objects
            for key in alts:
                if alternateTiles.get(key) is None:
                    alternateTiles[key] = [alts[key]]
                else:
                    duplicate = False
                    for tile in alternateTiles[key]:
                        a = tile.get("name")
                        b = alts[key].get("name")
                        if a == b:
                            duplicate = True
                    if not duplicate:
                        alternateTiles[key].extend([alts[key]])
    

        await ctx.send("Scraped preexisting tile data from `.ld` files.")
        self.bot.loading = False
        return alternateTiles
    
    @commands.command()
    @commands.is_owner()
    async def loaddata(self, ctx):
        '''
        Reloads tile data from `values.lua`, `editor_objectlist.lua` and `.ld` files.
        '''
        altTiles = await ctx.invoke(self.bot.get_command("loadchanges"))
        await ctx.invoke(self.bot.get_command("loadcolors"), alternateTiles = altTiles)
        await ctx.invoke(self.bot.get_command("loadeditor"))
        await ctx.invoke(self.bot.get_command("loadcustom"))
        await ctx.invoke(self.bot.get_command("dumpdata"))
        return await ctx.send("Done. Loaded all tile data.")

    @commands.command()
    @commands.is_owner()
    async def loadcolors(self, ctx, alternateTiles):
        '''
        Loads tile data from `values.lua.` and merges it with tile data from `.ld` files.
        '''

        self.tileData = {}
        altTiles = alternateTiles

        self.bot.loading = True
        # values.lua contains the data about which color (on the palette) is associated with each tile.
        lines = ""
        with open("values.lua", errors="replace") as colorvalues:
            lines = colorvalues.readlines()
        # Skips the parts we don't need
        tileslist = False
        # The name, ID and sprite of the currently handled tile
        name = ID = sprite = ""
        # The color of the currently handled tile
        colorRaw = ""
        color = []
        # Reads each line
        for line in lines:
            if tileslist:
                # Only consider certain lines ("objectXYZ =", "name = x", "sprite = y", "colour = {a,b}", "active = {a,b}")
                if line.startswith("\tobject"):
                    ID = line[1:10]
                elif line.startswith("\t\tname = "):
                    # Grabs only the name of the object
                    name = line[10:-3] # Magic numbers used to grab the perfect substring
                # This line has the format "\t\tsprite = \"name\",\n".
                elif line.startswith("\t\tsprite = "):
                    # Grabs only the name of the sprite
                    sprite = line[12:-3]
                # "\t\ttiling = [mode],\n"
                elif line.startswith("\t\ttiling = "):
                    tiling = line[11:-2]
                # These lines have the format "\t\t[active or colour] = {a,b}\n" where a,b are int.
                # "active = {a,b}" lines always come after "colour = {a,b}" so this check overwrites the color to "active".
                # The "active" line only exists for text tiles.
                # We prefer the active color of the text.
                # If you want the inactive colors, just remove the second condition check.
                elif line.startswith("\t\tcolour = ") or line.startswith("\t\tactive = "):
                    colorRaw = line[12:-3]
                    # Converts the string to a list 
                    # "{a,b}" --> [a,b]
                    seg = colorRaw.split(",")
                    color = [seg[i].strip() for i in range(2)]
                elif line.startswith("\t\ttype = "):
                    type_ = line[9:-2]
                # Signifies that the data for the current tile is over
                elif line == "\t},\n":
                    # Makes sure no fields are empty
                    # bool("") == False, but True for any other string
                    if bool(name) and bool(sprite) and bool(colorRaw) and bool(tiling):
                        # Alternate tile data (initialized with the original)
                        alts = {name:{"sprite":sprite, "color":color, "tiling":tiling, "source":"vanilla", "type":type_}}
                        # Looks for object replacements in the alternateTiles dict
                        if altTiles.get(ID) is not None:
                            # Each replacement for the object ID:
                            for value in altTiles[ID]:
                                # Sets fields to the alternate fields, if specified
                                altName = name
                                altSprite = sprite
                                altTiling = tiling
                                altColor = color
                                altType = type_
                                if value.get("name") != "":
                                    altName = value.get("name")
                                if value.get("sprite") != "":
                                    altSprite = value.get("sprite")
                                if value.get("color") != []: # This shouldn't ever be false
                                    altColor = value.get("color")
                                if value.get("tiling") != "":
                                    altTiling = value.get("tiling")
                                if value.get("type") != "":
                                    altType = value.get("type")
                                # Adds the change to the alts, but only if it's the first with that name
                                if name != altName:
                                    # If the name matches the name of an object already in the alt list
                                    if self.tileData.get(altName) is None:
                                        alts[altName] = {
                                            "sprite":altSprite, 
                                            "tiling":altTiling, 
                                            "color":altColor, 
                                            "type":altType,
                                            "source":"vanilla"
                                        }
                                        
                        # Adds each unique name-color pairs to the tileData dict
                        for key,value in alts.items():
                            self.tileData[key] = value
                    # Resets the fields
                    name = sprite = tiling = colorRaw = ""
                    color = []
            # Only begins checking for these lines once a certain point in the file has been passed
            elif line == "tileslist =\n":
                tileslist = True

        await ctx.send("Loaded default tile data from `values.lua`.")

        self.bot.loading = False

    @commands.command()
    @commands.is_owner()
    async def loadcustom(self, ctx):
        '''
        Loads custom tile data from `custom/*.json` into self.tileData
        '''
        
        # Load custom tile data from a json files
        customData = [x for x in listdir("custom") if x.endswith(".json")]
        # In alphabetical order, to make sure Patashu's redux mod overwrites the old mod
        customData.sort() 
        for f in customData:
            if f != "vanilla.json" and self.bot.vanillaOnly: break
            dat = None
            with open(f"custom/{f}") as fp:
                dat = json.load(fp)
            for tile in dat:
                name = tile["name"]
                # Rewrites the objects slightly
                rewritten = {}
                for key,value in tile.items():
                    if key != "name":
                        rewritten[key] = value
                # The sprite source (which folder to draw from)
                rewritten["source"] = f[:-5] # Trim ".json"
                if name is not None:
                    self.tileData[name] = rewritten

        await ctx.send("Loaded custom tile data from `custom/*.json`.")

    @commands.command()
    @commands.is_owner()
    async def loadeditor(self, ctx):
        '''
        Loads tile data from `editor_objectlist.lua` into `self.tileData`.
        '''

        lines = ""
        with open("editor_objectlist.lua", errors="replace") as objlist:
            lines = objlist.readlines()
        
        objects = {}
        parsingObjects = False
        name = tiling = tileType = sprite = ""
        color = None
        tags = None
        for line in lines:
            if line.startswith("editor_objlist = {"):
                parsingObjects = True
            if not parsingObjects:
                continue
            if line.startswith("\t},"):
                if sprite == "": sprite = name
                objects[name] = {"tiling":tiling,"type":tileType,"sprite":sprite,"color":color,"tags":tags,"source":"vanilla"}
                name = tiling = tileType = sprite = ""
                color = None
                tags = None
            elif line.startswith("\t\tname = \""):
                name = line[10:-3]
            elif line.startswith("\t\ttiling = "):
                tiling = line[11:-2]
            elif line.startswith("\t\tsprite = \""):
                sprite = line[12:-3]
            elif line.startswith("\t\ttype = "):
                tileType = line[9:-2]
            elif line.startswith("\t\tcolour = {"):
                if not color:
                    color = [x.strip() for x in line[12:-3].split(",")]
            elif line.startswith("\t\tcolour_active = {"):
                color = [x.strip() for x in line[19:-3].split(",")]
            elif line.startswith("\t\ttags = {"):
                ...

        self.tileData.update(objects)
        await ctx.send("Loaded tile data from `editor_objectlist.lua`.")

    @commands.command()
    @commands.is_owner()
    async def dumpdata(self, ctx):
        '''
        Dumps cached tile data from `self.tileData` into `tiledata.json` and `tilelist.txt`.
        '''

        maxLength = len(max(self.tileData, key=lambda x: len(x))) + 1

        with open("tilelist.txt", "wt") as allTiles:
            allTiles.write(f"{'*TILE* '.ljust(maxLength, '-')} *SOURCE*\n")
            allTiles.write("\n".join(sorted([(f"{(tile + ' ').ljust(maxLength, '-')} {data['source']}") for tile, data in self.tileData.items()])))

        # Dumps the gathered data to tiledata.json
        with open("cache/tiledata.json", "wt") as emoteFile:
            json.dump(self.tileData, emoteFile, indent=3)

        await ctx.send("Saved cached tile data.")
    
    @commands.command()
    @commands.is_owner()
    async def hidden(self, ctx):
        '''
        Lists all hidden commands.
        '''
        cmds = "\n".join([cmd.name for cmd in self.bot.commands if cmd.hidden])
        await self.bot.send(ctx, f"All hidden commands:\n{cmds}")

    @commands.command()
    @commands.is_owner()
    async def doc(self, ctx, command):
        '''
        Check a command's doc.
        '''
        description = self.bot.get_command(command).help
        await self.bot.send(ctx, f"Command doc for {command}:\n{description}")

    @commands.command()
    @commands.is_owner()
    async def loadtile(self, ctx, tile, palette):
        '''
        Load a single tile, given a single palette (or alternatively 'all' for all palettes)
        '''
        self.bot.loading = True
        # Some checks
        if self.tileData.get(tile) is None:
            return await self.bot.send(ctx, f"\"{tile}\" is not in the list of tiles.")
        palettes = [palette]
        if palette == "all":
            palettes = [pal[:-4] for pal in listdir("palettes") if pal.endswith(".png")]
        elif palette + ".png" not in listdir("palettes"):
            return await self.bot.send(ctx, f"\"{palette}\" is not a valid palette.")
            
        # Creates the directories for the palettes if they don't exist
        paletteColors = []
        for pal in palettes:
            Path(f"color/{pal}").mkdir(parents=True, exist_ok=True)

            # The palette image 
            paletteImg = Image.open("palettes/%s.png" % pal).convert("RGB")
            # The RGB values of the palette
            paletteColors.append([[(paletteImg.getpixel((x,y))) for y in range(5)] for x in range(7)])

        obj = self.tileData[tile]
        self.generateTileSprites(tile, obj, palettes, paletteColors)
        await ctx.send(f"Generated tile sprites for {tile}.")
        self.bot.loading = False

    @commands.command()
    @commands.is_owner()
    async def loadpalettes(self, ctx, args):
        '''
        Loads all tile sprites for the palettes given.
        '''
        
        self.bot.loading = True

        if isinstance(args, str):
            palettes = args.split(" ")
        else:
            palettes = args
        # Tests for a supplied palette
        for arg in palettes:
            if arg not in [s[:-4] for s in listdir("palettes")]:
                return await self.bot.send(ctx, "Supply a palette to load.")

        # The palette images
        # "hide" is a joke palette that doesn't render anything
        palettes = [p for p in palettes if p != "hide"]
        imgs = [Image.open("palettes/%s.png" % palette).convert("RGB") for palette in palettes]
        # The RGB values of the palette
        colors = [[[(img.getpixel((x,y))) for y in range(5)] for x in range(7)] for img in imgs]

        # Creates the directories for the palettes if they don't exist
        for palette in palettes:
            Path(f"color/{palette}").mkdir(parents=True, exist_ok=True)
        
        # Goes through each tile object in the tileData array
        i = 0
        total = len(self.tileData)
        for tile,obj in self.tileData.items():
            if i % 100 == 0:
                await ctx.send(f"{i} / {total}...")
            self.generateTileSprites(tile, obj, palettes, colors)
            i += 1
        await ctx.send(f"{total} / {total} tiles loaded.")

        self.bot.loading = False

    @commands.command()
    @commands.is_owner()
    async def make(self, ctx, name, color = ..., tileType = ...):
        two_rows = len(name) >= 4

        if two_rows:
            if not all(map(lambda c: c in self.letterWidths["small"], name)):
                return await ctx.send("Go on...")

        else:
            if not all(map(lambda c: c in self.letterWidths["big"], name)):
                return await ctx.send("Go on...")


    def initializeletters(self):
        big = {}
        small = {}
        for char in listdir("letters/big"):
            for width in listdir(f"letters/big/{char}"):
                big.setdefault(char, []).append(width)

        for char in listdir("letters/small"):
            for width in listdir(f"letters/small/{char}"):
                big.setdefault(char, []).append(width)

        self.letterWidths = {"big":big, "small":small}

    @commands.command()
    @commands.is_owner()
    async def loadletters(self, ctx):
        '''
        Scrapes individual letters from vanilla sprites.
        '''
        ignored = json.load(open("letterignore.json"))

        def check(data):
            return all([
                data["sprite"].startswith("text_"),
                data["source"] == "vanilla",
                data["sprite"] not in ignored,
                len(data["sprite"]) >= 7
            ])

        for data in filter(check, self.tileData.values()):
            sprite = data["sprite"]
            try:
                tileType = data["type"]
            except:
                print(data)
            self.loadletter(sprite, tileType)

        await ctx.send("pog")

    def loadletter(self, word, tileType):
        '''
        Scrapes letters from a sprite.
        '''
        chars = word[5:] # Strip "text_" prefix

        # Get the number of rows
        two_rows = len(chars) >= 4

        # Background plates for type-2 text,
        # in 1 bit per pixel depth
        plate_0 = Image.open("plates/plate_0.png").convert("RGBA").getchannel("A").convert("1")
        plate_1 = Image.open("plates/plate_1.png").convert("RGBA").getchannel("A").convert("1")
        plate_2 = Image.open("plates/plate_2.png").convert("RGBA").getchannel("A").convert("1")
        
        # Maps each character to three bounding boxes + images
        # (One box + image for each frame of animation)
        # char_pos : [((x1, y1, x2, y2), Image), ...]
        char_sizes = {}
        
        # Scrape the sprites for the sprite characters in each of the three frames
        for i, plate in enumerate([plate_0, plate_1, plate_2]):
            # Get the alpha channel in 1-bit depth
            alpha = Image.open(f"sprites/vanilla/{word}_0_{i + 1}.png") \
                .convert("RGBA") \
                .getchannel("A") \
                .convert("1")

            w, h = alpha.size
            
            # Type-2 text has inverted text on a background plate
            if tileType == "2":
                alpha = ImageChops.invert(alpha)
                alpha = ImageChops.logical_and(alpha, plate)


            # Get the point from which characters are seeked for
            x = 0
            if two_rows:
                y = h // 4
            else:
                y = h // 2

            # Flags
            skip = False
            
            # More than 1 bit per pixel is required for the flood fill
            alpha = alpha.convert("L")
            for j, char in enumerate(chars):
                if skip:
                    skip = False
                    continue

                while alpha.getpixel((x, y)) == 0:
                    if x == w - 1:
                        if two_rows and y == h // 4:
                            x = 0
                            y = 3 * h // 4
                        else:
                            break
                    else:
                        x += 1
                # There's a letter at this position
                else:
                    clone = alpha.copy()
                    ImageDraw.floodfill(clone, (x, y), 1) # 1 placeholder
                    clone = Image.eval(clone, lambda x: 255 if x == 1 else 0)
                    clone = clone.convert("1")
                    
                    # Get bounds of character blob 
                    x1, y1, x2, y2 = clone.getbbox()
                    # Run some checks
                    # Too wide => Skip 2 characters (probably merged two chars)
                    if x2 - x1 > (1.5 * w * (1 + two_rows) / len(chars)):
                        skip = True
                        continue
                    
                    # Too tall? Scrap the rest of the characters
                    if y2 - y1 > 1.5 * h / (1 + two_rows):
                        break
                    
                    # Remove character from sprite, push to char_sizes
                    alpha = ImageChops.difference(alpha, clone)
                    clone = clone.crop((x1, y1, x2, y2))
                    entry = ((x1, y1, x2, y2), clone)
                    char_sizes.setdefault((char, j), []).append(entry)
                    continue
                return

        saved = []
        # Save scraped characters
        for (char, _), entries in char_sizes.items():
            ...
            # All three frames clearly found the character in the sprite
            if len(entries) == 3:
                saved.append(char)
                x1_min = min(entries, key=lambda x: x[0][0])[0][0]
                y1_min = min(entries, key=lambda x: x[0][1])[0][1]
                x2_max = max(entries, key=lambda x: x[0][2])[0][2]
                y2_max = max(entries, key=lambda x: x[0][3])[0][3]

                now = int(datetime.utcnow().timestamp() * 1000)
                for i, ((x1, y1, _, _), img) in enumerate(entries):
                    frame = Image.new("1", (x2_max - x1_min, y2_max - y1_min))
                    frame.paste(img, (x1 - x1_min, y1 - y1_min))
                    height = "small" if two_rows else "big"
                    width = frame.size[0]
                    Path(f"letters/{height}/{char}/{width}").mkdir(parents=True, exist_ok=True)
                    frame.save(f"letters/{height}/{char}/{width}/{now}_{i}.png")

        # await ctx.send(f":) {saved}")


    @commands.command()
    @commands.is_owner()
    async def loadall(self, ctx):
        '''
        Reloads absolutely everything. (tile data, tile sprites)
        Avoid using this, as it takes minutes to complete.
        '''
        # Sends some feedback messages

        await ctx.send("Loading objects...")
        await ctx.invoke(self.bot.get_command("loaddata"))
        palettes = [palette[:-4] for palette in listdir("palettes") if palette.endswith(".png")] 
        # Strip ".png", ignore some files
        await ctx.invoke(self.bot.get_command("loadpalettes"), palettes)
        await ctx.send(f"{ctx.author.mention} Done.")

    def updateDebug(self):
        # Updates the debug file
        debugFile = "cache/debug.json"
        debugData = {"identifies":None,"resumes":None}

        # Prevent leaking
        yesterday = datetime.utcnow() - timedelta(days=1)
        identifiesDay = [event for event in self.identifies if event > yesterday]
        resumesDay = [event for event in self.resumes if event > yesterday]
        self.identifies = identifiesDay
        self.resumes = resumesDay

        debugData["identifies"] = identifiesDay
        debugData["resumes"] = resumesDay
        json.dump(debugData, open(debugFile, "w"), indent=2, default=lambda obj:obj.isoformat() if hasattr(obj, 'isoformat') else obj)

    def _clear_gateway_data(self):
        weekAgo = datetime.utcnow() - timedelta(days=7)
        to_remove = [index for index, dt in enumerate(self.resumes) if dt < weekAgo]
        for index in reversed(to_remove):
            del self.resumes[index]

        to_remove = [index for index, dt in enumerate(self.resumes) if dt < weekAgo]
        for index in reversed(to_remove):
            del self.identifies[index]
        
        # update debug data file
        self.updateDebug()
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        webhook = await self.bot.fetch_webhook(self.bot.webhookId)
        embed = discord.Embed(
            color = self.bot.embedColor,
            title = "Joined Guild",
            description = f"Joined {guild.name}."
        )
        embed.add_field(name="ID", value=str(guild.id))
        embed.add_field(name="Member Count", value=str(guild.member_count))
        await webhook.send(embed=embed)

    @commands.Cog.listener()
    async def on_socket_raw_send(self, data):
        # unconventional way to discern RESUMES from IDENTIFYs
        if '"op":2' not in data and '"op":6' not in data:
            return

        back_to_json = json.loads(data)
        if back_to_json['op'] == 2:
            self.identifies.append(datetime.utcnow())
            self.started = datetime.utcnow()
        else:
            self.resumes.append(datetime.utcnow())

        # don't want to permanently grow memory
        self._clear_gateway_data()   

        # update debug data file
        self.updateDebug()

def setup(bot):
    bot.add_cog(OwnerCog(bot))
