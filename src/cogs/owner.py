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

def multiply_color(fp, palettes, pixels):
    # fp: file path of the sprite
    # palettes: each palette name
    # pixels: the colors the tile should be recolored with

    unique_pixels = {}
    for palette,pixel in zip(palettes, pixels):
        unique_pixels.setdefault(pixel, []).append(palette)
    
    # Output images
    recolored = []
    output_palettes = unique_pixels.values()

    # Image to recolor from
    base = Image.open(fp).convert("RGBA")

    # Multiplies the R,G,B channel for each pixel value
    for pixel in unique_pixels:
        # New values
        new_r, new_g, new_b = pixel
        # New channels
        arr = np.asarray(base, dtype='uint16')
        r_c, g_c, b_c, a_c = arr.T
        r_c, g_c, b_c = new_r*r_c / 256, new_g*g_c / 256, new_b*b_c / 256
        out = np.stack((r_c.T,g_c.T,b_c.T,a_c.T),axis=2).astype('uint8')
        RGBA = Image.fromarray(out)
        # Adds to list
        recolored.append(RGBA)

    return zip(recolored, output_palettes)

def get_sprite_variants(sprite, tiling):
    '''
    Opens the associated sprites from data/sprites/
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
        sprite_numbers = [0,1,2,3] # Animation
    if tiling == "3" and sprite != "goose": # Basically for belts only (anim + dirs)
        sprite_numbers = [0,1,2,3, # Animation right
                        8,9,10,11, # Animation up
                        16,17,18,19, # Animation left
                        24,25,26,27] # Animation down

    if tiling == "3" and sprite == "goose": # For Goose (anim + dirs)
        sprite_numbers = [0,1,2,3, # Animation right
                        # Goose has no up animations ¯\_(ツ)_/¯
                        16,17,18,19, # Animation left
                        24,25,26,27] # Animation down

    elif tiling == "2" and sprite != "robot": # Baba, Keke, Me and Anni have some wonky sprite variations
        sprite_numbers = [0,1,2,3, # Moving animation to the right
                        7, # Sleep up
                        8,9,10, 11, # Moving animation up
                        15, # Sleep left
                        16,17,18,19, #Moving animation left
                        23, # Sleep down
                        24,25,26,27, # Moving animation down
                        31] # Sleep right

    elif tiling == "2" and sprite == "robot": 
        # Robot has no sleep animations but is a character ¯\_(ツ)_/¯
        sprite_numbers = [0,1,2,3, # Moving animation to the right
                        8,9,10, 11, # Moving animation up
                        16,17,18,19, #Moving animation left
                        24,25,26,27] # Moving animation down

    elif tiling == "1": # "Tiling" objects
        sprite_numbers = [i for i in range(16)]

    elif tiling == "0": # "Directional" objects have these sprite variations: 
        sprite_numbers = [0,8,16,24]

    else: # No tiling
        sprite_numbers = [0]
    
    return sprite_numbers
    
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
        self.tile_data = {}
        self.identifies = []
        self.resumes = []
        # Loads the caches
        # Loads the tile colors, if it exists
        colors_file = "cache/tiledata.json"
        if stat(colors_file).st_size != 0:
            self.tile_data = json.load(open(colors_file))
            
        # Loads the alternate tiles if possible
        # Loads debug data, if any
        debug_file = "cache/debug.json"
        if stat(debug_file).st_size != 0:
            debug_data = json.load(open(debug_file), object_pairs_hook=load_with_datetime)
            self.identifies = debug_data.get("identifies")
            self.resumes = debug_data.get("resumes")

        self.initializeletters()
        
        # Are assets loading?
        self.bot.loading = False

    def generate_tile_sprites(self, tile, obj, palettes, colors):
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
        sprite_variants = get_sprite_variants(sprite, tiling)

        # Saves the tile sprites
        single_frame = ["smiley", "hi", "plus"] # Filename is of the format "smiley_1.png"
        no_variants = ["default"] # Filenames are of the format "default_<1/2/3>.png"
        for variant in sprite_variants:
            if tile in single_frame or tile.startswith("icon"): # Icons have a single frame
                if tile == "icon":
                    paths = [f"data/sprites/{source}/icon.png" for i in range(3)]
                else:
                    paths = [f"data/sprites/{source}/{sprite}_1.png" for i in range(3)]
            elif tile in no_variants:
                paths = [f"data/sprites/{source}/{sprite}_{i + 1}.png" for i in range(3)]
            else:
                # Paths should only be of length 3
                paths = [f"data/sprites/{source}/{sprite}_{variant}_{i + 1}.png" for i in range(3)]
            
            # Changes the color of each image, then saves it
            for i,fp in enumerate(paths):
                pixels = [img[x][y] for img in colors]
                recolored = multiply_color(fp, palettes, pixels)
                # Saves the colored images to target/color/[palette]/ given that the image may be identical for some palettes
                # Recolored images, palettes each image is associated with
                for img,uses in recolored:
                    # Each associated palette
                    for use in uses:
                        # This saves some redundant computing time spent recoloring the same image multiple times
                        # (up to >10 for certain color indices)
                        img.save(f"target/color/{use}/{tile}-{variant}-{i}-.png", format="PNG")
            
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
        identifies_day = [event for event in self.identifies if event > yesterday]
        resumes_day = [event for event in self.resumes if event > yesterday]
        i_count = len(identifies_day)
        r_count = len(resumes_day)

        global_rate_limit = not self.bot.http._global_over.is_set()

        msg = discord.Embed(
            title="Debug",
            description="".join([f"IDENTIFYs in the past 24 hours: {i_count}\n",
                f"RESUMEs in the past 24 hours: {r_count}\n",
                f"Global rate limit: {global_rate_limit}"]),
            color=self.bot.embed_color
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
        
        alternate_tiles = {}

        levels = [l for l in listdir("data/levels/vanilla") if l.endswith(".ld")]
        for level in levels:
            # Reads each line of the level file
            lines = ""
            with open(f"data/levels/vanilla/{level}") as fp:
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
                            color_raw = line[:][17:-1]
                            # Splits the color into a list 
                            # "a,b" -> [a,b]
                            color = color_raw.split(",")
                            if not alts[ID].get("color"):
                                alts[ID]["color"] = color
                        # Sets the changed color (active text only), overrides previous
                        elif line.startswith("activecolour=", 10):
                            color_raw = line[:][23:-1]
                            # Splits the color into a list 
                            # "a,b" -> [a,b]
                            color = color_raw.split(",")
                            alts[ID]["color"] = color
                    
            # Adds the data to the list of changed objects
            for key in alts:
                if alternate_tiles.get(key) is None:
                    alternate_tiles[key] = [alts[key]]
                else:
                    duplicate = False
                    for tile in alternate_tiles[key]:
                        a = tile.get("name")
                        b = alts[key].get("name")
                        if a == b:
                            duplicate = True
                    if not duplicate:
                        alternate_tiles[key].extend([alts[key]])
    

        await ctx.send("Scraped preexisting tile data from `.ld` files.")
        self.bot.loading = False
        return alternate_tiles
    
    @commands.command()
    @commands.is_owner()
    async def loaddata(self, ctx):
        '''
        Reloads tile data from `data/values.lua`, `data/editor_objectlist.lua` and `.ld` files.
        '''
        alt_tiles = await ctx.invoke(self.bot.get_command("loadchanges"))
        await ctx.invoke(self.bot.get_command("loadcolors"), alternate_tiles = alt_tiles)
        await ctx.invoke(self.bot.get_command("loadeditor"))
        await ctx.invoke(self.bot.get_command("loadcustom"))
        await ctx.invoke(self.bot.get_command("dumpdata"))
        return await ctx.send("Done. Loaded all tile data.")

    @commands.command()
    @commands.is_owner()
    async def loadcolors(self, ctx, alternate_tiles):
        '''
        Loads tile data from `data/values.lua.` and merges it with tile data from `.ld` files.
        '''

        self.tile_data = {}
        alt_tiles = alternate_tiles

        self.bot.loading = True
        # values.lua contains the data about which color (on the palette) is associated with each tile.
        lines = ""
        with open("data/values.lua", errors="replace") as colorvalues:
            lines = colorvalues.readlines()
        # Skips the parts we don't need
        tileslist = False
        # The name, ID and sprite of the currently handled tile
        name = ID = sprite = ""
        # The color of the currently handled tile
        color_raw = ""
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
                    color_raw = line[12:-3]
                    # Converts the string to a list 
                    # "{a,b}" --> [a,b]
                    seg = color_raw.split(",")
                    color = [seg[i].strip() for i in range(2)]
                elif line.startswith("\t\ttype = "):
                    type_ = line[9:-2]
                # Signifies that the data for the current tile is over
                elif line == "\t},\n":
                    # Makes sure no fields are empty
                    # bool("") == False, but True for any other string
                    if bool(name) and bool(sprite) and bool(color_raw) and bool(tiling):
                        # Alternate tile data (initialized with the original)
                        alts = {name:{"sprite":sprite, "color":color, "tiling":tiling, "source":"vanilla", "type":type_}}
                        # Looks for object replacements in the alternateTiles dict
                        if alt_tiles.get(ID) is not None:
                            # Each replacement for the object ID:
                            for value in alt_tiles[ID]:
                                # Sets fields to the alternate fields, if specified
                                alt_name = name
                                alt_sprite = sprite
                                alt_tiling = tiling
                                alt_color = color
                                alt_type = type_
                                if value.get("name") != "":
                                    alt_name = value.get("name")
                                if value.get("sprite") != "":
                                    alt_sprite = value.get("sprite")
                                if value.get("color") != []: # This shouldn't ever be false
                                    alt_color = value.get("color")
                                if value.get("tiling") != "":
                                    alt_tiling = value.get("tiling")
                                if value.get("type") != "":
                                    alt_type = value.get("type")
                                # Adds the change to the alts, but only if it's the first with that name
                                if name != alt_name:
                                    # If the name matches the name of an object already in the alt list
                                    if self.tile_data.get(alt_name) is None:
                                        alts[alt_name] = {
                                            "sprite":alt_sprite, 
                                            "tiling":alt_tiling, 
                                            "color":alt_color, 
                                            "type":alt_type,
                                            "source":"vanilla"
                                        }
                                        
                        # Adds each unique name-color pairs to the tile data dict
                        for key,value in alts.items():
                            self.tile_data[key] = value
                    # Resets the fields
                    name = sprite = tiling = color_raw = ""
                    color = []
            # Only begins checking for these lines once a certain point in the file has been passed
            elif line == "tileslist =\n":
                tileslist = True

        await ctx.send("Loaded default tile data from `data/values.lua`.")

        self.bot.loading = False

    @commands.command()
    @commands.is_owner()
    async def loadcustom(self, ctx):
        '''
        Loads custom tile data from `data/custom/*.json` into self.tile_data
        '''
        
        # Load custom tile data from a json files
        custom_data = [x for x in listdir("data/custom") if x.endswith(".json")]
        # In alphabetical order, to make sure Patashu's redux mod overwrites the old mod
        custom_data.sort() 
        for f in custom_data:
            if f != "vanilla.json" and self.bot.vanilla_only: break
            dat = None
            with open(f"data/custom/{f}") as fp:
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
                    self.tile_data[name] = rewritten

        await ctx.send("Loaded custom tile data from `data/custom/*.json`.")

    @commands.command()
    @commands.is_owner()
    async def loadeditor(self, ctx):
        '''
        Loads tile data from `data/editor_objectlist.lua` into `self.tile_data`.
        '''

        lines = ""
        with open("data/editor_objectlist.lua", errors="replace") as objlist:
            lines = objlist.readlines()
        
        objects = {}
        parsing_objects = False
        name = tiling = tile_type = sprite = ""
        color = None
        tags = None
        for line in lines:
            if line.startswith("editor_objlist = {"):
                parsing_objects = True
            if not parsing_objects:
                continue
            if line.startswith("\t},"):
                if sprite == "": sprite = name
                objects[name] = {"tiling":tiling,"type":tile_type,"sprite":sprite,"color":color,"tags":tags,"source":"vanilla"}
                name = tiling = tile_type = sprite = ""
                color = None
                tags = None
            elif line.startswith("\t\tname = \""):
                name = line[10:-3]
            elif line.startswith("\t\ttiling = "):
                tiling = line[11:-2]
            elif line.startswith("\t\tsprite = \""):
                sprite = line[12:-3]
            elif line.startswith("\t\ttype = "):
                tile_type = line[9:-2]
            elif line.startswith("\t\tcolour = {"):
                if not color:
                    color = [x.strip() for x in line[12:-3].split(",")]
            elif line.startswith("\t\tcolour_active = {"):
                color = [x.strip() for x in line[19:-3].split(",")]
            elif line.startswith("\t\ttags = {"):
                ...

        self.tile_data.update(objects)
        await ctx.send("Loaded tile data from `data/editor_objectlist.lua`.")

    @commands.command()
    @commands.is_owner()
    async def dumpdata(self, ctx):
        '''
        Dumps cached tile data from `self.tile_data` into `cache/tiledata.json` and `target/tilelist.txt`.
        '''

        max_length = len(max(self.tile_data, key=lambda x: len(x))) + 1

        with open("target/tilelist.txt", "wt") as all_tiles:
            all_tiles.write(f"{'*TILE* '.ljust(max_length, '-')} *SOURCE*\n")
            all_tiles.write("\n".join(sorted([(f"{(tile + ' ').ljust(max_length, '-')} {data['source']}") for tile, data in self.tile_data.items()])))

        # Dumps the gathered data to tiledata.json
        with open("cache/tiledata.json", "wt") as emote_file:
            json.dump(self.tile_data, emote_file, indent=3)

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
        if self.tile_data.get(tile) is None:
            return await self.bot.send(ctx, f"\"{tile}\" is not in the list of tiles.")
        palettes = [palette]
        if palette == "all":
            palettes = [pal[:-4] for pal in listdir("data/palettes") if pal.endswith(".png")]
        elif palette + ".png" not in listdir("data/palettes"):
            return await self.bot.send(ctx, f"\"{palette}\" is not a valid palette.")
            
        # Creates the directories for the palettes if they don't exist
        palette_colors = []
        for pal in palettes:
            Path(f"target/color/{pal}").mkdir(parents=True, exist_ok=True)

            # The palette image 
            palette_img = Image.open(f"data/palettes/{pal}.png").convert("RGB")
            # The RGB values of the palette
            palette_colors.append([[(palette_img.getpixel((x,y))) for y in range(5)] for x in range(7)])

        obj = self.tile_data[tile]
        self.generate_tile_sprites(tile, obj, palettes, palette_colors)
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
            if arg not in [s[:-4] for s in listdir("data/palettes")]:
                return await self.bot.send(ctx, "Supply a palette to load.")

        # The palette images
        # "hide" is a joke palette that doesn't render anything
        palettes = [p for p in palettes if p != "hide"]
        imgs = [Image.open(f"data/palettes/{palette}.png").convert("RGB") for palette in palettes]
        # The RGB values of the palette
        colors = [[[(img.getpixel((x,y))) for y in range(5)] for x in range(7)] for img in imgs]

        # Creates the directories for the palettes if they don't exist
        for palette in palettes:
            Path(f"target/color/{palette}").mkdir(parents=True, exist_ok=True)
        
        # Goes through each tile object in the tile data array
        i = 0
        total = len(self.tile_data)
        for tile,obj in self.tile_data.items():
            if i % 100 == 0:
                await ctx.send(f"{i} / {total}...")
            self.generate_tile_sprites(tile, obj, palettes, colors)
            i += 1
        await ctx.send(f"{total} / {total} tiles loaded.")

        self.bot.loading = False

    @commands.command()
    @commands.is_owner()
    async def make(self, ctx, name, color = ..., tile_type = ...):
        two_rows = len(name) >= 4

        if two_rows:
            if not all(map(lambda c: c in self.letter_widths["small"], name)):
                return await ctx.send("Go on...")

        else:
            if not all(map(lambda c: c in self.letter_widths["big"], name)):
                return await ctx.send("Go on...")


    def initializeletters(self):
        big = {}
        small = {}
        for char in listdir("target/letters/big"):
            for width in listdir(f"target/letters/big/{char}"):
                big.setdefault(char, []).append(width)

        for char in listdir("target/letters/small"):
            for width in listdir(f"target/letters/small/{char}"):
                big.setdefault(char, []).append(width)

        self.letter_widths = {"big":big, "small":small}

    @commands.command()
    @commands.is_owner()
    async def loadletters(self, ctx):
        '''
        Scrapes individual letters from vanilla sprites.
        '''
        ignored = json.load(open("cache/letterignore.json"))

        def check(data):
            return all([
                data["sprite"].startswith("text_"),
                data["source"] == "vanilla",
                data["sprite"] not in ignored,
                len(data["sprite"]) >= 7
            ])

        for data in filter(check, self.tile_data.values()):
            sprite = data["sprite"]
            try:
                tile_type = data["type"]
            except:
                print(data)
            self.loadletter(sprite, tile_type)

        await ctx.send("pog")

    def loadletter(self, word, tile_type):
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
            alpha = Image.open(f"data/sprites/vanilla/{word}_0_{i + 1}.png") \
                .convert("RGBA") \
                .getchannel("A") \
                .convert("1")

            w, h = alpha.size
            
            # Type-2 text has inverted text on a background plate
            if tile_type == "2":
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
                    Path(f"target/letters/{height}/{char}/{width}").mkdir(parents=True, exist_ok=True)
                    frame.save(f"target/letters/{height}/{char}/{width}/{now}_{i}.png")

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
        palettes = [palette[:-4] for palette in listdir("data/palettes") if palette.endswith(".png")] 
        # Strip ".png", ignore some files
        await ctx.invoke(self.bot.get_command("loadpalettes"), palettes)
        await ctx.send(f"{ctx.author.mention} Done.")

    def update_debug(self):
        # Updates the debug file
        debug_file = "cache/debug.json"
        debug_data = {"identifies":None,"resumes":None}

        # Prevent leaking
        yesterday = datetime.utcnow() - timedelta(days=1)
        identifies_day = [event for event in self.identifies if event > yesterday]
        resumes_day = [event for event in self.resumes if event > yesterday]
        self.identifies = identifies_day
        self.resumes = resumes_day

        debug_data["identifies"] = identifies_day
        debug_data["resumes"] = resumes_day
        json.dump(debug_data, open(debug_file, "w"), indent=2, default=lambda obj:obj.isoformat() if hasattr(obj, 'isoformat') else obj)

    def _clear_gateway_data(self):
        week_ago = datetime.utcnow() - timedelta(days=7)
        to_remove = [index for index, dt in enumerate(self.resumes) if dt < week_ago]
        for index in reversed(to_remove):
            del self.resumes[index]

        to_remove = [index for index, dt in enumerate(self.resumes) if dt < week_ago]
        for index in reversed(to_remove):
            del self.identifies[index]
        
        # update debug data file
        self.update_debug()
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        webhook = await self.bot.fetch_webhook(self.bot.webhook_id)
        embed = discord.Embed(
            color = self.bot.embed_color,
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
        self.update_debug()

def setup(bot):
    bot.add_cog(OwnerCog(bot))
