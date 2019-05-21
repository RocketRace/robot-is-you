import ast
import discord
import json
import numpy     as np

from discord.ext import commands
from os          import listdir, mkdir, stat
from PIL         import Image

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
    
class ownerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tileColors = []
        self.alternateTiles = {}
        # Loads the tile colors, if it exists
        colorsFile = "tilecolors.json"
        if stat(colorsFile).st_size != 0:
            self.tileColors = json.load(open(colorsFile))
        # Loads the alternate tiles if possible
        altFile = "alternatetiles.json"
        if stat(altFile).st_size != 0:
            self.alternateTiles = json.load(open(altFile))

        # Are assets loading?
        self.notLoading = True

    # Evaluates input if you're the owner of the bot (me)
    # TODO: sandbox it
    @commands.command(name="eval")
    @commands.is_owner()
    async def evaluate(self, ctx, *, content: str):
        success = True
        result = ""
        try:
            result = eval(content)
        except Exception as e:
            result = e
            success = False
        if success:
            await ctx.send("Evaluated successfully:\n%s" % result)
        else:
            await ctx.send("An exception occurred%s" % result)

    @commands.is_owner()
    @commands.command(name="exec")
    async def execute(self, ctx, *, cmd):
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
        await ctx.send("Result:\n" + str(result))


    # Sends a message in the specified channel
    @commands.command()
    @commands.is_owner()
    async def announce(self, ctx, channel, title, *, content):
        t = title
        t = t.replace("_", " ")
        embed = discord.Embed(title=t, type="rich", description=content, colour=0x00ffff)
        await ctx.message.channel_mentions[0].send(" ", embed=embed)

    @commands.command()
    @commands.is_owner()
    async def loadchanges(self, ctx):
        self.notLoading = False
        
        self.alternateTiles = {}

        levels = listdir("levels")
        for level in levels:
            # Reads each line of the level file
            fp = open("levels/%s" % level)
            lines = fp.readlines()
            fp.close()

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
                            alts[alt] = {"name":"", "sprite":"", "color":[]}
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
                if self.alternateTiles.get(key) == None:
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

                          
        # Custom sprites: Hempuli
        self.alternateTiles["object001"].append({"name":"hempuli","sprite":"hempuli","color":[4,2]})
        self.alternateTiles["object001"].append({"name":"text_hempuli","sprite":"text_hempuli","color":[4,2]})
        
        # Saves the data of ALL the themes to the json file
        alternateFile = open("alternatetiles.json", "wt")
        alternateFile.seek(0)
        alternateFile.truncate()
        json.dump(self.alternateTiles, alternateFile, indent=3)
        alternateFile.close()
        self.notLoading = True

    @commands.command()
    @commands.is_owner()
    async def loadcolors(self, ctx):
        # Reads values.lua and scrapes the tile data from there

        self.tileColors = []

        self.notLoading = False
        # values.lua contains the data about which color (on the palette) is associated with each tile.
        colorvalues = open("values.lua")
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
                # This line has the format "\t\tsprite = \"name\"\n".
                elif line.startswith("\t\tsprite = "):
                    # Grabs only the name of the sprite
                    sprite = line[12:-3]
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
                    if bool(name) and bool(sprite) and bool(colorRaw):
                        # Alternate tile data (initialized with the original)
                        alts = [{"name":name, "sprite":sprite, "color":color}]
                        # Looks for object replacements in the alternateTiles dict
                        if self.alternateTiles.get(ID) != None:
                            # Each replacement for the object ID:
                            for obj in self.alternateTiles[ID]:
                                # Sets fields to the alternate fields, if specified
                                altName = name
                                altSprite = sprite
                                altColor = color
                                if obj.get("name") != "":
                                    altName = obj.get("name")
                                if obj.get("sprite") != "":
                                    altSprite = obj.get("sprite")
                                if obj.get("color") != []: # This shouldn't ever be false
                                    altColor = obj.get("color")
                                # Adds the change to the alts, but only if it's the first with that name
                                if name != altName:
                                    # If the name matches the name of an object already in the alt list
                                    duplicate = False
                                    for t in self.tileColors:
                                        if t["name"] == altName:
                                            duplicate = True
                                    if not duplicate:
                                        alts.append({"name":altName, "sprite":altSprite, "color":altColor})
                        # Adds each unique name-color pairs to the tileColors dict
                        for obj in alts:
                            self.tileColors.append(obj)
                    # Resets the fields
                    name = sprite = colorRaw = ""
                    color = []
            # Only begins checking for these lines once a certain point in the file has been passed
            elif line == "tileslist =\n":
                tileslist = True

        # Manual patches to the tile list for overall enjoyment.
        # Not all the information could be scrapped automatically, at least reliably.

        # Set all letter tiles to the same color
        for obj in self.tileColors:
            if obj["name"].startswith("text_") and len(obj["name"]) == 6:
                obj["color"] = ["0", "1"]

        # Dumps the gathered data to tilecolors.json and tilesprites.json
        emotefile = open("tilecolors.json", "wt")
        # Clears the file first
        emotefile.seek(0)
        emotefile.truncate()
        json.dump(self.tileColors, emotefile, indent=3)
        emotefile.close()

        self.notLoading = True

    @commands.command()
    @commands.is_owner()
    async def loadpalette(self, ctx, arg):
        
        self.notLoading = False

        # Tests for a supplied palette
        if arg not in [str[:-4] for str in listdir("palettes")]:
            await ctx.send("Supply a palette to load.")
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
            for obj in self.tileColors:
                # Fetches the tile data
                name = obj["name"]
                sprite = obj["sprite"]
                color = obj["color"]
                # For convenience
                x,y = [int(n) for n in color]
            
                # Opens the three associated sprites from sprites/
                # Only uses the first variation of the sprite ("_0_")
                files = ["sprites/%s_0_%s.png" % (sprite, i + 1) for i in range(3)]
                # Changes the color of each image
                framesColor = [multiplyColor(fp, paletteColors[x][y]) for fp in files]
                # Saves the colored images to /color/[palette]/
                [framesColor[i].save("color/%s/%s-%s-.png" % (palette, name, i), format="PNG") for i in range(len(framesColor))]
        self.notLoading = True

    @commands.command()
    @commands.is_owner()
    async def loadall(self, ctx):
        msg = await ctx.send("Loading object changes...")
        await ctx.invoke(self.bot.get_command("loadchanges"))
        await msg.edit(content="Loading themes... Done.")
        await msg.edit(content="Loading themes... Done.\nLoading colors...")
        await ctx.invoke(self.bot.get_command("loadcolors"))
        await msg.edit(content="Loading themes... Done.\nLoading colors... Done.")
        

        palettes = ["default.png"]#listdir("palettes")
        total = len(palettes)

        await msg.edit(content="Loading themes... Done.\nLoading colors... Done.\nLoading palettes... (0/%s)" % total)
        i = 0
        for palette in [fp[:-4] for fp in palettes]:
            await ctx.invoke(self.bot.get_command("loadpalette"), palette)
            i += 1
            await msg.edit(content="Loading themes... Done.\nLoading colors... Done.\nLoading palettes... (%s/%s)" % (i, total))
        await msg.edit(content="Loading themes... Done.\nLoading colors... Done.\nLoading palettes... Done.")

def setup(bot):
    bot.add_cog(ownerCog(bot))


