import ast
import asyncio
import discord
import json
import os

from datetime     import datetime, timedelta
from discord.ext  import commands
from pathlib      import Path
from PIL          import Image, ImageDraw, ImageChops

def load_with_datetime(pairs, format='%Y-%m-%dT%H:%M:%S.%f'):
    '''Load json + datetime objects, in the speficied format.
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
    
    def bot_check(self, ctx):
        return ctx.author.id not in self.blacklist

    def __init__(self, bot):
        self.bot = bot
        self.tile_data = {}
        self.identifies = []
        self.resumes = []
        self.blacklist = []
        # Loads the caches
        # Loads the tile colors, if it exists
        colors_file = "cache/tiledata.json"
        if os.stat(colors_file).st_size != 0:
            self.tile_data = json.load(open(colors_file))
            
        # Loads the alternate tiles if possible
        # Loads debug data, if any
        debug_file = "cache/debug.json"
        if os.stat(debug_file).st_size != 0:
            debug_data = json.load(open(debug_file), object_pairs_hook=load_with_datetime)
            self.identifies = debug_data.get("identifies")
            self.resumes = debug_data.get("resumes")

        bl_file = "cache/blacklist.json"
        if os.stat(debug_file).st_size != 0:
            self.blacklist = json.load(open(bl_file))

        self.initialize_letters()
        
        # Are assets loading?
        self.bot.loading = False
            
    @commands.command(aliases=["load", "reload"])
    @commands.is_owner()
    async def reloadcog(self, ctx, cog = None):
        '''Reloads extensions within the bot while the bot is running.'''
        if cog is None:
            extensions = [a for a in self.bot.extensions.keys()]
            for extension in extensions:
                self.bot.reload_extension(extension)
            await ctx.send("Reloaded all extensions.")
        elif "src.cogs." + cog in self.bot.extensions.keys():
            self.bot.reload_extension("src.cogs." + cog)
            await ctx.send(f"Reloaded extension `{cog}` from `src/cogs/{cog}.py`.")
        else:
            await ctx.send("Unknown extension provided.")

    @commands.command(aliases=["reboot"])
    @commands.is_owner()
    async def restart(self, ctx):
        '''Restarts the bot process.'''
        await ctx.send("Restarting bot process...")
        self.bot.exit_code = 1
        await self.bot.logout()

    @commands.command(aliases=["kill", "yeet"])
    @commands.is_owner()
    async def logout(self, ctx):
        '''Kills the bot process.'''
        if ctx.invoked_with == "yeet":
            await ctx.send("Yeeting bot process...")
        else:
            await ctx.send("Killing bot process...")
        await self.bot.logout()

    @commands.command()
    @commands.is_owner()
    async def debug(self, ctx):
        '''Gives some debug stats.'''
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

    @commands.command()
    @commands.is_owner()
    async def ban(self, ctx, user: int):
        self.blacklist.append(user)
        with open("cache/blacklist.json", "w") as f:
            json.dump(self.blacklist, f)
        await ctx.send(f"{user} bent.")

    @commands.command()
    @commands.is_owner()
    async def leave(self, ctx, guild: int = None):
        if guild is None:
            await ctx.send("Bye!")
            await ctx.guild.leave()
        else:
            try:
                await self.bot.get_guild(guild).leave()
                await ctx.send(f"Left {guild}.")
            except:
                await ctx.send(f"Couldn't leave {guild}.")

    @commands.command()
    @commands.is_owner()
    async def loadchanges(self, ctx):
        '''Scrapes alternate tile data from level metadata (`.ld`) files.'''
        self.bot.loading = True
        
        alternate_tiles = {}

        levels = [l for l in os.listdir("data/levels/vanilla") if l.endswith(".ld")]
        with open("config/editortileignore.json") as fp:
            ignored_tiles = json.load(fp)
        for level in levels:
            # Reads each line of the level file
            lines = ""
            with open(f"data/levels/vanilla/{level}", errors="ignore") as fp:
                lines = fp.readlines()

            IDs = []
            alts = {}

            # Loop through the lines
            for line in lines:
                # Only considers lines starting with objectXYZ
                if line.startswith("changed="):
                    if len(line) > 16:
                        IDs = line[8:].strip().split(",")[:-1]
                        alts = {ID: {"name":"", "sprite":"", "tiling":"", "color":[], "active":[],"type":""} for ID in IDs}
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
                            # if not alts[ID].get("color"):
                            alts[ID]["color"] = color
                        # Sets the changed color (active text only), overrides previous
                        elif line.startswith("activecolour=", 10):
                            color_raw = line[:][23:-1]
                            # Splits the color into a list 
                            # "a,b" -> [a,b]
                            active = color_raw.split(",")
                            alts[ID]["active"] = active
                    
            # Adds the data to the list of changed objects
            for key in alts:
                if alternate_tiles.get(key) is None:
                    if alts[key].get("name") in ignored_tiles:
                        continue
                    alternate_tiles[key] = [alts[key]]
                else:
                    if alts[key].get("name") in ignored_tiles:
                        continue
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
        '''Reloads tile data from `data/values.lua`, `data/editor_objectlist.lua` and `.ld` files.'''
        alt_tiles = await ctx.invoke(self.bot.get_command("loadchanges"))
        await ctx.invoke(self.bot.get_command("loadcolors"), alternate_tiles = alt_tiles)
        await ctx.invoke(self.bot.get_command("loadeditor"))
        await ctx.invoke(self.bot.get_command("loadcustom"))
        await ctx.invoke(self.bot.get_command("dumpdata"))
        return await ctx.send("Done. Loaded all tile data.")

    @commands.command()
    @commands.is_owner()
    async def loadcolors(self, ctx, alternate_tiles):
        '''Loads tile data from `data/values.lua.` and merges it with tile data from `.ld` files.'''
        print(len(self.tile_data))
        self.tile_data = {}
        alt_tiles = alternate_tiles

        self.bot.loading = True
        # values.lua contains the data about which color (on the palette) is associated with each tile.
        lines = ""
        with open("data/values.lua", errors="replace") as colorvalues:
            lines = colorvalues.readlines()
        # Skips the parts we don't need
        tileslist = False
        # Data
        name = ID = sprite = tiling = ""
        # Color
        color_raw = active_raw = ""
        color = active = []
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
                elif line.startswith("\t\tcolour = "):
                    color_raw = line[12:-3]
                    # Converts the string to a list 
                    # "{a,b}" --> [a,b]
                    seg = color_raw.split(",")
                    color = [seg[i].strip() for i in range(2)]
                elif line.startswith("\t\tactive = "):
                    active_raw = line[12:-3]
                    seg = active_raw.split(",")
                    active = [seg[i].strip() for i in range(2)]
                elif line.startswith("\t\ttype = "):
                    type_ = line[9:-2]
                # Signifies that the data for the current tile is over
                elif line == "\t},\n":
                    # Makes sure no fields are empty
                    # bool("") == False, but True for any other string
                    if all((name, sprite, color_raw, active_raw, tiling)):
                        # Alternate tile data (initialized with the original)
                        self.tile_data[name] = {"sprite":sprite, "color":color, "active":active, "tiling":tiling, "source":"vanilla", "type":type_}
                        # Looks for object replacements in the alternateTiles dict
                        if alt_tiles.get(ID) is not None:
                            # Each replacement for the object ID:
                            for value in alt_tiles[ID]:
                                # Sets fields to the alternate fields, if specified
                                alt_name = name
                                alt_sprite = sprite
                                alt_tiling = tiling
                                alt_color = color
                                alt_active = active
                                alt_type = type_
                                if value.get("name") != "":
                                    alt_name = value.get("name")
                                if value.get("sprite") != "":
                                    alt_sprite = value.get("sprite")
                                if value.get("color") != []: # This shouldn't ever be false
                                    alt_color = value.get("color")
                                if value.get("active") != []: # This shouldn't ever be false
                                    alt_active = value.get("active")
                                if value.get("tiling") != "":
                                    alt_tiling = value.get("tiling")
                                if value.get("type") != "":
                                    alt_type = value.get("type")
                                # Adds the change to the alts, but only if it's the first with that name
                                if name != alt_name:
                                    # If the name matches the name of an object already in the alt list
                                    if self.tile_data.get(alt_name) is None:
                                        self.tile_data[alt_name] = {
                                            "sprite":alt_sprite, 
                                            "tiling":alt_tiling, 
                                            "color":alt_color, 
                                            "active":alt_active,
                                            "type":alt_type,
                                            "source":"vanilla"
                                        } 
                    # Resets the fields
                    name = sprite = tiling = color_raw = active_raw = ""
                    color = active = []
            # Only begins checking for these lines once a certain point in the file has been passed
            elif line == "tileslist =\n":
                tileslist = True

        await ctx.send("Loaded default tile data from `data/values.lua`.")

        self.bot.loading = False
        print(len(self.tile_data))

    @commands.command()
    @commands.is_owner()
    async def loadcustom(self, ctx):
        '''Loads custom tile data from `data/custom/*.json` into self.tile_data'''
        
        # Load custom tile data from a json files
        custom_data = [x for x in os.listdir("data/custom") if x.endswith(".json")]
        # In alphabetical order, to make sure Patashu's redux mod overwrites the old mod
        custom_data.sort() 
        for f in custom_data:
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
        '''Loads tile data from `data/editor_objectlist.lua` into `self.tile_data`.'''
        print(len(self.tile_data))

        lines = ""
        with open("data/editor_objectlist.lua", errors="replace") as objlist:
            lines = objlist.readlines()
        
        objects = {}
        parsing_objects = False
        name = tiling = tile_type = sprite = ""
        color = active = None
        tags = None
        for line in lines:
            if line.startswith("editor_objlist = {"):
                parsing_objects = True
            if not parsing_objects:
                continue
            if line.startswith("\t},"):
                if sprite == "": sprite = name
                objects[name] = {"tiling":tiling,"type":tile_type,"sprite":sprite,"color":color,"active":active,"tags":tags,"source":"vanilla"}
                name = tiling = tile_type = sprite = ""
                color = active = None
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
                color = [x.strip() for x in line[12:-3].split(",")]
            elif line.startswith("\t\tcolour_active = {"):
                active = [x.strip() for x in line[19:-3].split(",")]
            elif line.startswith("\t\ttags = {"):
                ...

        self.tile_data.update(objects)
        print(len(self.tile_data))
        await ctx.send("Loaded tile data from `data/editor_objectlist.lua`.")

    @commands.command()
    @commands.is_owner()
    async def dumpdata(self, ctx):
        '''Dumps cached tile data from `self.tile_data` into `cache/tiledata.json` and `target/tilelist.txt`.'''

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
        '''Lists all hidden commands.'''
        cmds = "\n".join([cmd.name for cmd in self.bot.commands if cmd.hidden])
        await self.bot.send(ctx, f"All hidden commands:\n{cmds}")

    @commands.command()
    @commands.is_owner()
    async def doc(self, ctx, command):
        '''Check a command's docstring.'''
        description = self.bot.get_command(command).help
        await self.bot.send(ctx, f"Command doc for {command}:\n{description}")

    def initialize_letters(self):
        big = {}
        small = {}
        for char in os.listdir("target/letters/big"):
            if char != ".DS_Store":
                for width in os.listdir(f"target/letters/big/{char}"):
                    if width != ".DS_Store":
                        big.setdefault(char, set()).add(int(width))

        for char in os.listdir("target/letters/small"):
            if char != ".DS_Store":
                for width in os.listdir(f"target/letters/small/{char}"):
                    if width != ".DS_Store":
                        small.setdefault(char, set()).add(int(width))

        os.system("cp -r data/letters target")

        self.letter_widths = {"big":big, "small":small}

    @commands.command()
    @commands.is_owner()
    async def loadletters(self, ctx):
        '''Scrapes individual letters from vanilla sprites.'''
        ignored = json.load(open("config/letterignore.json"))

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

        self.initialize_letters()

        await ctx.send("pog")

    def loadletter(self, word, tile_type):
        '''Scrapes letters from a sprite.'''
        chars = word[5:] # Strip "text_" prefix

        # Get the number of rows
        two_rows = len(chars) >= 4

        # Background plates for type-2 text,
        # in 1 bit per pixel depth
        plate_0 = Image.open("data/plates/plate_0.png").convert("RGBA").getchannel("A").convert("1")
        plate_1 = Image.open("data/plates/plate_1.png").convert("RGBA").getchannel("A").convert("1")
        plate_2 = Image.open("data/plates/plate_2.png").convert("RGBA").getchannel("A").convert("1")
        
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
