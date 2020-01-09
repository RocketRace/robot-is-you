import ast
import asyncio
import discord
import json
import numpy      as np

from datetime     import datetime, timedelta
from discord.ext  import commands
from os           import listdir, mkdir, stat
from PIL          import Image
from string       import ascii_lowercase
from subprocess   import Popen, PIPE, STDOUT
from time         import time

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
    # Opens the associated sprites from sprites/
    # Use every sprite variant, the amount based on the tiling type

    # Sprite variants follow this scheme:

    # == IF NOT TILING TYPE 1 ==
    # Change by 1 := Change in animation
    # -> 0,1,2,3 := Regular animation
    # -> 7 := Sleeping animation
    # Change by 8 := Change in direction

    # == IF TYLING TYPE 1 ==
    # 0  := None adjacent
    # 1  := Right
    # 2  := Up
    # 3  := Up & Right
    # 4  := Left
    # 5  := Left & Right
    # 6  := Left & Up
    # 7  := Left & Right & Up
    # 8  := Down
    # 9  := Down & Right
    # 10 := Down & Up
    # 11 := Down & Right & Up
    # 12 := Down & Left
    # 13 := Down & Left & Right
    # 14 := Down & Left & Up
    # 15 := Down & Left & Right & Up

    if tiling == "4": # Animated, non-directional
        spriteNumbers = [0,1,2,3] # Animation
    if tiling == "3" and sprite != "goose": # Basically for belts only (anim + dirs)
        spriteNumbers = [0,1,2,3, # Animation right
                        8,9,10,11, # Animation up
                        16,17,18,19, # Animation left
                        24,25,26,27] # Animation down

    if tiling == "3" and sprite == "goose": # Basically for belts only (anim + dirs)
        spriteNumbers = [0,1,2,3, # Animation right
                        # Goose has no up animations
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

    elif tiling == "2" and sprite == "robot": # No sleep sprite for robot
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
    
def insert_returns(body):
    # insert return stmt if the last expression is a expression statement
    if isinstance(body[-1], ast.Expr):
        body[-1] = ast.Return(body[-1].value)
        ast.fix_missing_locations(body[-1])

    # for if statements, we insert returns into the body and the orelse
    if isinstance(body[-1], ast.If):
        insert_returns(body[-1].body)
        insert_returns(body[-1].orelse)

    # for with blocks, again we insert returns into the body
    if isinstance(body[-1], ast.With):
        insert_returns(body[-1].body)

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
        self.tileColors = {}
        self.identifies = []
        self.resumes = []
        # Loads the caches
        # Loads the tile colors, if it exists
        colorsFile = "cache/tilecolors.json"
        if stat(colorsFile).st_size != 0:
            self.tileColors = json.load(open(colorsFile))
        # Loads the alternate tiles if possible
        # Loads debug data, if any
        debugFile = "cache/debug.json"
        if stat(debugFile).st_size != 0:
            debugData = json.load(open(debugFile), object_pairs_hook=load_with_datetime)
            self.identifies = debugData.get("identifies")
            self.resumes = debugData.get("resumes")
        
        # Are assets loading?
        self.bot.loading = False

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
        singleFrame = ["smiley", "hi"] # Filename is of the format "smiley_1.png"
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
        Scrapes additional tile data from level metadata files.
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
                            alts[alt] = {"name":"", "sprite":"", "tiling":"", "color":[]}
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
                        elif line.startswith("tiling=", 10):
                            alts[ID]["tiling"] = line[:][17:-1]
                        # Sets the changed color (all tiles)
                        elif line.startswith("colour=", 10):
                            colorRaw = line[:][17:-1]
                            # Splits the color into a list 
                            # "a,b" -> [a,b]
                            color = colorRaw.split(",")
                            alts[ID]["color"] = color
                        # Sets the changed color (active text only)
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
        
        # Saves the data of ALL the themes to alternatetiles.json
        with open("cache/alternatetiles.json", "wt") as alternateFile:
            json.dump(alternateTiles, alternateFile, indent=3)

        await ctx.send("Loaded additional tile data from .ld files.")
        self.bot.loading = False
        return alternateTiles
    
    @commands.command()
    @commands.is_owner()
    async def loaddata(self, ctx):
        '''
        Reloads tile data from values.lua and .ld files.
        '''
        altTiles = await ctx.invoke(self.bot.get_command("loadchanges"))
        await ctx.invoke(self.bot.get_command("loadcolors"), alternateTiles = altTiles)
        return await ctx.send("Done. Loaded all tile data.")

    @commands.command()
    @commands.is_owner()
    async def loadcolors(self, ctx, alternateTiles):
        '''
        Loads initial tile data from values.lua.
        '''
        # Reads values.lua and scrapes the tile data from there

        self.tileColors = {}
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
                if line.startswith("\t\tname = "):
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
                # Signifies that the data for the current tile is over
                elif line == "\t},\n":
                    # Makes sure no fields are empty
                    # bool("") == False, but True for any other string
                    if bool(name) and bool(sprite) and bool(colorRaw) and bool(tiling):
                        # Alternate tile data (initialized with the original)
                        alts = {name:{"sprite":sprite, "color":color, "tiling":tiling, "source":"vanilla"}}
                        # Looks for object replacements in the alternateTiles dict
                        if altTiles.get(ID) is not None:
                            # Each replacement for the object ID:
                            for value in altTiles[ID]:
                                # Sets fields to the alternate fields, if specified
                                altName = name
                                altSprite = sprite
                                altTiling = tiling
                                altColor = color
                                if value.get("name") != "":
                                    altName = value.get("name")
                                if value.get("sprite") != "":
                                    altSprite = value.get("sprite")
                                if value.get("color") != []: # This shouldn't ever be false
                                    altColor = value.get("color")
                                if value.get("tiling") != "":
                                    altTiling = value.get("tiling")
                                # Adds the change to the alts, but only if it's the first with that name
                                if name != altName:
                                    # If the name matches the name of an object already in the alt list
                                    if self.tileColors.get(altName) is None:
                                        alts[altName] = {"sprite":altSprite, "tiling":altTiling, "color":altColor, "source":"vanilla"}
                        # Adds each unique name-color pairs to the tileColors dict
                        for key,value in alts.items():
                            self.tileColors[key] = value
                    # Resets the fields
                    name = sprite = tiling = colorRaw = ""
                    color = []
            # Only begins checking for these lines once a certain point in the file has been passed
            elif line == "tileslist =\n":
                tileslist = True

        # Load custom tile data from a json files
        customData = listdir("custom")
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
                    self.tileColors[name] = rewritten

        with open("tilelist.txt", "wt") as allTiles:
            allTiles.write("\n".join(sorted([tile for tile in self.tileColors])))

        # Dumps the gathered data to tilecolors.json
        with open("cache/tilecolors.json", "wt") as emoteFile:
            json.dump(self.tileColors, emoteFile, indent=3)

        await ctx.send("Loaded initial tile data.")

        self.bot.loading = False
    
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
        if self.tileColors.get(tile) is None:
            return await self.bot.send(ctx, f"\"{tile}\" is not in the list of tiles.")
        palettes = [palette]
        if palette == "all":
            palettes = [pal[:-4] for pal in listdir("palettes")]
        elif palette + ".png" not in listdir("palettes"):
            return await self.bot.send(ctx, f"\"{palette}\" is not a valid palette.")
            
        # Creates the directories for the palettes if they don't exist
        paletteColors = []
        for pal in palettes:
            try:
                mkdir("color/%s" % pal)
            except FileExistsError:
                pass

            # The palette image 
            paletteImg = Image.open("palettes/%s.png" % pal).convert("RGB")
            # The RGB values of the palette
            paletteColors.append([[(paletteImg.getpixel((x,y))) for y in range(5)] for x in range(7)])

        obj = self.tileColors[tile]
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
            try:
                mkdir("color/%s" % palette)
            except FileExistsError:
                pass
        
        # Goes through each tile object in the tileColors array
        i = 0
        total = len(self.tileColors)
        for tile,obj in self.tileColors.items():
            if i % 100 == 0:
                await ctx.send(f"{i} / {total}...")
            self.generateTileSprites(tile, obj, palettes, colors)
            i += 1
        await ctx.send(f"{total} / {total} tiles loaded.")

        self.bot.loading = False
    
    @commands.command()
    @commands.is_owner()
    async def loadall(self, ctx):
        '''
        Reloads absolutely everything. (tile data, tile sprites, TODO levels)
        Avoid using this, as it takes minutes to complete.
        '''
        # Sends some feedback messages

        await ctx.send("Loading objects...")
        altTiles = await ctx.invoke(self.bot.get_command("loadchanges"))
        await ctx.send("Loading colors...")
        await ctx.invoke(self.bot.get_command("loadcolors"), alternateTiles=altTiles)
        await ctx.send("Loading palettes...")
        palettes = [palette[:-4] for palette in listdir("palettes") if palette not in [".DS_Store"]] 
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
        else:
            self.resumes.append(datetime.utcnow())

        # don't want to permanently grow memory
        self._clear_gateway_data()   

        # update debug data file
        self.updateDebug()

def setup(bot):
    bot.add_cog(OwnerCog(bot))
