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
    
class ownerCog(commands.Cog):
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

        # Are assets loading?
        self.notLoading = True

    # Evaluates input if you're the owner of the bot (me)
    # TODO: sandbox it
    @commands.command(name="eval")
    @commands.is_owner()
    async def eval(self, ctx, *, content: str):
        success = True
        result = ""
        try:
            result = eval(content)
        except Exception as e:
            result = e
            success = False
        if success:
            await ctx.send(f"```\n✅ Evaluated successfully:\n{result}\n```")
        else:
            await ctx.send(f"```\n🚫 An exception occurred:\n{result}\n```")

    @commands.command()
    @commands.is_owner()
    async def loadthemes(self, ctx):
        # Loads the sprites, names and colors for each "alternate object", that is, an object with data NOT in values.lua

        # Disables all other commands for now
        self.notLoading = False

        # Clears existing data
        altFile = open("alternatetiles.json", "wt")
        altFile.seek(0)
        altFile.truncate()
        altFile.close()

        # Finds each theme
        themes = listdir("themes")
        for theme in themes:
            # Reads each line of the theme file
            fp = open("themes/%s" % theme)
            lines = fp.readlines()
            fp.close()

            # The ID, name and sprite of the changed object
            ID = name = sprite = ""
            # The color of the changed object
            colorRaw = ""
            color = []

            # Loop through the lines
            for line in lines:
                # Only considers lines starting with objectXYZ
                if line.startswith("object"):
                    # Tests if a new object is being manipulated, unless it's the very first one
                    if line[:9] != ID and bool(ID):
                        # Adds the data to the alternateTiles dict
                        # Creates a new key if the dict doesn't already have one
                        if self.alternateTiles.get(ID) == None:
                            # Note that if any of the variables is an empty string, that data is saved
                            # The alternate tile checker will consider an empty string "no change".
                            self.alternateTiles[ID] = [{"name":name, "sprite":sprite, "color":color}]
                        else:
                            # Each ID has a list of alternative versions - each new one is appended
                            self.alternateTiles[ID].append({"name":name, "sprite":sprite, "color":color})
                        # Resets the values
                        ID = name = sprite = ""
                    ID = line[:9]
                    # If the line matches "objectZYX_name="
                    # Sets the changed name
                    if line.startswith("name=", 10):
                        # Magic numbers used to grab only the name of the sprite
                        # Same is used below for sprites/colors
                        name = line[15:-1]
                    # Sets the changed sprite
                    elif line.startswith("image=", 10):
                        sprite = line[16:-1]
                    # Sets the changed color (all tiles)
                    elif line.startswith("colour=", 10):
                        colorRaw = line[17:-1]
                        # Splits the color into a list 
                        # "a,b" -> [a,b]
                        color = colorRaw.split(",")
                    # Sets the changed color (active text only)
                    elif line.startswith("activecolour=", 10):
                        colorRaw = line[23:-1]
                        # Splits the color into a list 
                        # "a,b" -> [a,b]
                        color = colorRaw.split(",")

        # Saves the data of ALL the themes to the json file
        alternateFile = open("alternatetiles.json", "wt")
        json.dump(self.alternateTiles, alternateFile, indent=3)
        alternateFile.close()

        # Enables commands again
        self.NotLoading = True

    @commands.command()
    @commands.is_owner()
    async def loadcolors(self, ctx):
        # Reads values.lua and scrapes the tile data from there

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
                                # Adds the change to the alts
                                alts.append({"name":altName, "sprite":altSprite, "color":altColor})
                        # Removes duplicate objects in alts
                        uniqueAlts = list({alt["name"] : alt for alt in alts}.values())
                        # Adds each unique name-color pairs to the tileColors dict
                        for obj in uniqueAlts:
                            self.tileColors[obj["name"]] = [obj["sprite"], obj["color"]]               
                    # Resets the fields
                    name = sprite = colorRaw = ""
                    color = []
            # Only begins checking for these lines once a certain point in the file has been passed
            elif line == "tileslist =\n":
                tileslist = True
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
            
            # Goes through each tile object in the tileColors dict
            for name in self.tileColors:
                # Fetches the tile data
                sprite = self.tileColors[name][0]
                color = self.tileColors[name][1]
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
        msg = await ctx.send("Loading themes...")
        await ctx.invoke(self.bot.get_command("loadthemes"))
        await msg.edit(content="Loading themes... Done.")
        await msg.edit(content="Loading themes... Done.\nLoading colors...")
        await ctx.invoke(self.bot.get_command("loadcolors"))
        await msg.edit(content="Loading themes... Done.\nLoading colors... Done.")
        

        palettes = listdir("palettes")
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


