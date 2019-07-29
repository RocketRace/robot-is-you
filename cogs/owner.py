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

def multiplyColor(fp, RGB):
    newR, newG, newB = RGB
    
    # Saves the alpha channel
    img = Image.open(fp).convert("RGBA")
    A = img.getchannel("A")

    # Multiplies the R,G,B channels with the input RGB values
    R,G,B = img.convert("RGB").split()
    R = R.point(lambda px: int(px * newR / 255))
    G = G.point(lambda px: int(px * newG / 255))
    B = B.point(lambda px: int(px * newB / 255))
    
    # Merges the channels and returns the RGBA image
    RGBA = Image.merge("RGBA", (R, G, B, A))
    return RGBA

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
    if tiling == "3": # Basically for belts only (anim + dirs)
        spriteNumbers = [0,1,2,3, # Animation right
                        8,9,10,11, # Animation up
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
    
class OwnerCog(commands.Cog, name="Admin", command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self.tileColors = {}
        self.alternateTiles = {}
        # Loads the tile colors, if it exists
        colorsFile = "tilecolors.json"
        if stat(colorsFile).st_size != 0:
            self.tileColors = json.load(open(colorsFile))
        # Loads the alternate tiles if possible
        altFile = "alternatetiles.json"
        if stat(altFile).st_size != 0:
            self.alternateTiles = json.load(open(altFile))
        self.bot.loop.create_task(self.statSaver())

        self.identifies = []
        self.resumes = []
        self.keepSaving = True

        # Are assets loading?
        self.bot.loading = False

    def generateTileSprites(self, tile, obj, palette, paletteColors):
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
        for variant in spriteVariants:
            if tile.startswith("icon"):
                if tile == "icon":
                    paths = [f"sprites/{source}/icon.png" for i in range(3)]
                else:
                    paths = [f"sprites/{source}/{sprite}_1.png" for i in range(3)]
            else:
                paths = [f"sprites/{source}/{sprite}_{variant}_{i + 1}.png" for i in range(3)]
            # Changes the color of each image
            framesColor = [multiplyColor(fp, paletteColors[x][y]) for fp in paths]
            # Saves the colored images to /color/[palette]/
            [framesColor[i].save(f"color/{palette}/{tile}-{variant}-{i}-.png", format="PNG") for i in range(len(framesColor))             
            
    @commands.command()
    @commands.is_owner()
    async def debug(self, ctx):
        yesterday = datetime.utcnow() - timedelta(days=1)
        identifiesDay = sum([1 for event in self.identifies if event > yesterday])
        resumesDay = sum([1 for event in self.resumes if event > yesterday])

        globalRateLimit = not self.bot.http._global_over.is_set()

        msg = discord.Embed(
            title="Debug",
            description="".join([f"IDENTIFYs in the past 24 hours: {identifiesDay}\n",
                f"RESUMEs in the past 24 hours: {resumesDay}\n",
                f"Global rate limit: {globalRateLimit}"]),
            color=0x00ffff
        )

        await self.bot.send(ctx, " ", embed=msg)
        

    @commands.is_owner()
    @commands.command(name="eval")
    async def _eval(self, ctx, *, cmd):
        """Evaluates input.
        Input is interpreted as newline seperated statements.
        If the last statement is an expression, that is the return value.
        Usable globals:
          - `bot`: the bot instance
          - `discord`: the discord module
          - `commands`: the discord.ext.commands module
          - `ctx`: the invokation context
          - `__import__`: the builtin `__import__` function
        Such that `>eval 1 + 1` gives `2` as the result.
        The following invokation will cause the bot to send the text '9'
        to the channel of invokation and return '3' as the result of evaluating
        >eval ```
        a = 1 + 2
        b = a * 2
        await ctx.send(a + b)
        a
        ```
        """
        fn_name = "_eval_expr"

        cmd = cmd.strip("` ")

        # add a layer of indentation
        cmd = "\n".join(f"    {i}" for i in cmd.splitlines())

        # wrap in async def body
        body = f"async def {fn_name}():\n{cmd}"

        parsed = ast.parse(body)
        body = parsed.body[0].body

        insert_returns(body)

        env = {
            'bot': ctx.bot,
            'discord': discord,
            'commands': commands,
            'ctx': ctx,
            '__import__': __import__
        }
        exec(compile(parsed, filename="<ast>", mode="exec"), env)

        result = (await eval(f"{fn_name}()", env))
        await self.bot.send(ctx, "Result:\n" + str(result))


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
        self.bot.loading = True
        
        self.alternateTiles = {}

        levels = listdir("levels")
        for level in levels:
            # Reads each line of the level file
            lines = ""
            with open("levels/%s" % level) as fp:
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
                if self.alternateTiles.get(key) is None:
                    self.alternateTiles[key] = [alts[key]]
                else:
                    duplicate = False
                    for tile in self.alternateTiles[key]:
                        a = tile.get("name")
                        b = alts[key].get("name")
                        if a == b:
                            duplicate = True
                    if not duplicate:
                        self.alternateTiles[key].extend([alts[key]])
        
        # Saves the data of ALL the themes to alternatetiles.json
        with open("alternatetiles.json", "wt") as alternateFile:
            json.dump(self.alternateTiles, alternateFile, indent=3)

        await ctx.send("Done.")
        self.bot.loading = False

    @commands.command()
    @commands.is_owner()
    async def loadcolors(self, ctx):
        # Reads values.lua and scrapes the tile data from there

        self.tileColors = {}

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
                        alts = {name:{"sprite":sprite, "color":color, "tiling":tiling}}
                        # Looks for object replacements in the alternateTiles dict
                        if self.alternateTiles.get(ID) is not None:
                            # Each replacement for the object ID:
                            for value in self.alternateTiles[ID]:
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
                                        alts[altName] = {"sprite":altSprite, "tiling":altTiling, "color":altColor}
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
            allTiles.write("\n".join([tile for tile in self.tileColors]))

        # Dumps the gathered data to tilecolors.json
        with open("tilecolors.json", "wt") as emoteFile:
            json.dump(self.tileColors, emoteFile, indent=3)

        await ctx.send("Done.")

        self.bot.loading = False

    @commands.command()
    @commands.is_owner()
    async def loadtile(self, ctx, tile, palette):
        self.bot.loading = True
        # Some checks
        if self.tileColors.get(tile) is None:
            return await self.bot.send(ctx, f"\"{tile}\" is not in the list of tiles.")
        palettes = [palette]
        if palette == "all":
            palettes = [pal[:-4] for pal in listdir("palettes")]
        elif palette + ".png" not in listdir("palettes"):
            return await self.bot.send(ctx, f"\"{palette}\" is not a valid palette.")
            
        for pal in palettes:
            # Creates the directories for the palettes if they don't exist
            try:
                mkdir("color/%s" % pal)
            except FileExistsError:
                pass

            # The palette image 
            paletteImg = Image.open("palettes/%s.png" % pal).convert("RGB")
            # The RGB values of the palette
            paletteColors = [[(paletteImg.getpixel((x,y))) for y in range(5)] for x in range(7)]

            obj = self.tileColors[tile]
            self.generateTileSprites(tile, obj, pal, paletteColors)
        await ctx.send("Done.")
        self.bot.loading = False

    @commands.command()
    @commands.is_owner()
    async def loadpalette(self, ctx, arg):
        
        self.bot.loading = True

        # Tests for a supplied palette
        if arg not in [str[:-4] for str in listdir("palettes")]:
            await self.bot.send(ctx, "Supply a palette to load.")
        else: 
            # The palette name
            palette = arg
            # The palette image 
            paletteImg = Image.open("palettes/%s.png" % palette).convert("RGB")
            # The RGB values of the palette
            paletteColors = [[(paletteImg.getpixel((x,y))) for y in range(5)] for x in range(7)]

            # Creates the directories for the palettes if they don't exist
            try:
                mkdir("color/%s" % palette)
            except FileExistsError:
                pass
            
            # Goes through each tile object in the tileColors array
            for tile,obj in self.tileColors.items():
                self.generateTileSprites(tile, obj, palette, paletteColors)

        self.bot.loading = False

    @commands.command()
    @commands.is_owner()
    async def pull(self, ctx):
        await ctx.send("Pulling the new version from github...")
        puller = Popen(["git", "pull"], cwd="/home/pi/Desktop/robot-private/", stdout=PIPE, stderr=STDOUT, universal_newlines=True)
        process = True
        # Checks if the process has completed every half a second
        i = 0
        returncode = None
        while process:
            returncode = puller.poll()
            i += 0.5
            if returncode is None:
                if i > 30:
                    process = False
                else:
                    await asyncio.sleep(0.5)
            else:
                process = False
        stdout, stderr = puller.communicate()
        # stderr is always None
        if stderr is None:
            if i > 30:
                await ctx.send("`git pull` took more than 30 seconds to execute. Aborting.")
                puller.terminate()
            else:
                await ctx.send(f"`git pull` exited with code {returncode}. Output: ```\n{stdout}\n```")
    

    @commands.command()
    @commands.is_owner()
    async def loadall(self, ctx):
        # Sends some feedback messages

        await ctx.send("Loading objects...")
        await ctx.invoke(self.bot.get_command("loadchanges"))
        await ctx.send("Loading colors...")
        await ctx.invoke(self.bot.get_command("loadcolors"))
        await ctx.send("Loading palettes...")
        

        # Loads every palette
        palettes = listdir("palettes")
        total = len(palettes)

        i = 0
        for palette in [fp[:-4] for fp in palettes]:
            await ctx.send(f" {i}/{total}")
            await ctx.invoke(self.bot.get_command("loadpalette"), palette)
            i += 1
        await ctx.send(f"Loading palettes... {total}/{total}")
        await ctx.send(f"{ctx.author.mention} Done.")

    def _clear_gateway_data(self):
        weekAgo = datetime.utcnow() - timedelta(days=7)
        to_remove = [index for index, dt in enumerate(self.resumes) if dt < weekAgo]
        for index in reversed(to_remove):
            del self.resumes[index]

        to_remove = [index for index, dt in enumerate(self.resumes) if dt < weekAgo]
        for index in reversed(to_remove):
            del self.identifies[index]

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

def setup(bot):
    bot.add_cog(OwnerCog(bot))
