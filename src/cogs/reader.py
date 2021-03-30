from __future__ import annotations
import asyncio
import configparser
import io
from typing import Any, Dict, List, Optional, TextIO, Tuple
import aiohttp
import base64
import json
import zlib

from discord.ext import commands, tasks
from os          import listdir, stat

def flatten(x: int, y: int, width: int) -> int:
    '''Return the flattened position of a coordinate in a grid of specified width'''
    return int(y) * width + int(x)

def try_index(string: str, value: str) -> int:
    '''Returns the index of a substring within a string.
    Returns -1 if not found.
    '''
    index = -1
    try:
        index = string.index(value)
    except:
        pass
    return index

class Grid:
    '''This stores the information of a single Baba level, in a format readable by the renderer.'''
    def __init__(self, filename: str, source: str):
        '''Initializes a blank grid, given a path to the level file. 
        This should not be used; you should use Reader.read_map() instead to generate a filled grid.
        '''
        # The location of the level
        self.fp = f"data/levels/{source}/{filename}.l"
        self.filename = filename
        self.source = source
        # Basic level information
        self.name = ""
        self.subtitle = ""
        self.palette = ""
        self.images: List[str] = []
        # Object information
        self.width = 0
        self.height = 0
        self.cells: List[List[Item]] = []
        # Parent level and map identification
        self.parent = None
        self.map_id = None
        self.style = None
        self.number = None
        self.extra = None
    
    def unflatten(self) -> List[List[List[str]]]:
        '''Returns an unflattened version of the grid.'''
        height = self.height
        width = self.width
        return [
            [
                [
                    "".join([
                        o.name or "error",
                        f":{o.direction * 8}" if o.direction is not None else "",
                        ":" + "/".join(tuple(map(str, o.color))) if o.color is not None else ""
                    ])
                    for o in self.cells[y * width + x]
                ]
                for x in range(width)
            ]
            for y in range(height)
        ]

class Item:
    '''Represents an object within a level.
    This may be a regular object, a path object, a level object, a special object or empty.
    '''
    def __init__(self, *, ID: Optional[int] = None, obj: Optional[str] = None, name: Optional[str] = None, color: Optional[Tuple[int, int]] = None, position: int = None, direction: int = None, extra = None, layer: int = 0):
        '''Returns an Item with the given parameters.'''
        self.ID = ID
        self.obj = obj
        self.name = name
        self.color = color
        self.position = position
        self.direction = direction
        self.extra = extra
        self.layer = layer

    def copy(self) -> Item:
        '''Returns a copy of the item.'''
        return Item(ID=self.ID, obj=self.obj, name=self.name, color=self.color, position=self.position, direction=self.direction, extra=self.extra, layer=self.layer)

    @classmethod
    def edge(cls) -> Item:
        '''Returns an Item representing an edge tile.'''
        return Item(ID=0, obj="edge", name="edge", layer=20)
    
    @classmethod
    def empty(cls) -> Item:
        '''Returns an Item representing an empty tile.'''
        return Item(ID=-1, obj="empty", name="empty", layer=0)
    
    @classmethod
    def level(cls, color: Tuple[int, int] = (0, 3)) -> Item:
        '''Returns an Item representing a level object.'''
        return Item(ID=-2, obj="level", name="level", color=color, layer=20)

class Reader(commands.Cog, command_attrs=dict(hidden=True)):
    '''A class for parsing the contents of level files.'''
    def __init__(self, bot: commands.Bot):
        '''Initializes the Reader cog.
        Populates the default objects cache from a data/values.lua file.
        '''
        self.bot = bot
        self.defaults_by_id = {}
        self.defaults_by_object = {}
        self.defaults_by_name = {}
        self.level_data = {} # id: level metadata
        self.custom_levels = {} # code: level metadata
        # Intermediary, please don't access
        self.parent_levels = {}

        with open("data/values.lua") as reader:
            line = None
            while line != "":
                line = reader.readline()
                index = try_index(line, "tileslist =")
                if index == -1:
                    continue
                elif index == 0:
                    # Parsing begins
                    self.read_objects(reader)
                    break
        
        # Level data cache
        levelcache = "cache/leveldata.json"
        if stat(levelcache).st_size != 0:
            self.level_data = json.load(open(levelcache))
        custom = "cache/customlevels.json"
        if stat(custom).st_size != 0:
            self.custom_levels = json.load(open(custom))
        self.update_custom_levels.start()

    async def render_custom(self, code: str) -> Dict[str, Any]:
        '''Renders a custom level. code should be valid (but is checked regardless)'''
        async with aiohttp.request("GET", f"https://baba-is-bookmark.herokuapp.com/api/level/raw/l?code={code}") as resp:
            resp.raise_for_status()
            data = await resp.json()
            b64 = data["data"]
            decoded = base64.b64decode(b64)
            raw_l = io.BytesIO(decoded)
        async with aiohttp.request("GET", f"https://baba-is-bookmark.herokuapp.com/api/level/raw/ld?code={code}") as resp:
            resp.raise_for_status()
            data = await resp.json()
            raw_s = data["data"]
            raw_ld = io.StringIO(raw_s)

        grid = self.read_map(code, source="custom", data=raw_l)
        grid = self.read_metadata(grid, data=raw_ld, custom=True)

        objects = grid.unflatten()
        # Strips the borders from the render
        # (last must be popped before first to preserve order)
        objects.pop(grid.height - 1)
        objects.pop(0)
        for row in objects:
            row.pop(grid.width - 1)
            row.pop(0)
        out = f"target/renders/custom/{code}.gif"
        cog = self.bot.get_cog("Baba Is You")
        tiles = cog.handle_variants(objects, tile_borders=True, is_level=True)
        cog.render(tiles, grid.width, grid.height, palette=grid.palette, background=(0, 4), out=out)
        
        self.custom_levels[code] = metadata = {
            "name": grid.name,
            "subtitle": grid.subtitle,
            "style": grid.style,
            "number": grid.number,
            "images": grid.images,
            "palette": grid.palette,
            "width": grid.width,
            "height": grid.height,
            "source": "custom",
            "author": grid.extra
        }
        return metadata

    def render_map(
        self, 
        filename: str, 
        source: str, 
        initialize: bool = False, 
        remove_borders: bool = False, 
        keep_background: bool = False, 
        tile_borders: bool = False
    ) -> Dict[str, Any]:
        '''Loads and renders a level, given its file path and source. 
        Shaves off the borders if specified.
        '''
        # Data
        grid = self.read_map(filename, source=source)
        grid = self.read_metadata(grid, initialize=initialize)
        objects = grid.unflatten()

        # Shave off the borders:
        if remove_borders:
            objects.pop(grid.height - 1)
            objects.pop(0)
            for row in objects:
                row.pop(grid.width - 1)
                row.pop(0)

        # Handle sprite variants
        cog = self.bot.get_cog("Baba Is You")
        tiles = cog.handle_variants(objects, tile_borders=tile_borders, is_level=True)

        # (0,4) is the color index for level backgrounds
        background = (0,4) if keep_background else None

        # Render the level
        cog.render(
            tiles,
            grid.width,
            grid.height,
            palette=grid.palette,
            images=grid.images,
            image_source=grid.source,
            background=background,
            out=f"target/renders/{grid.source}/{grid.filename}.gif",
            use_overridden_colors=True
        )
        
        # Return level metadata
        return {
            "name": grid.name,
            "subtitle": grid.subtitle,
            "images": grid.images,
            "palette": grid.palette,
            "filename": grid.filename,
            "map_id": grid.map_id,
            "parent": grid.parent,
            "width": grid.width,
            "height": grid.height,
            "source": grid.source,
            "number": grid.number,
            "style": grid.style,
        }

    @commands.command()
    @commands.is_owner()
    async def loadmap(self, ctx, source: str, filename: str, initialize: bool = False):
        '''Loads a given level. Initializes the level tree if so specified.'''
        # Parse and render
        metadata = self.render_map(
            filename, 
            source=source, 
            initialize=initialize, 
            remove_borders=True,
            keep_background=True,
            tile_borders=True
        )
        # This should mostly just be false
        if initialize:
            self.clean_metadata({filename: metadata})
        await ctx.send(f"Rendered level at `{source}/{filename}`.")

    def clean_metadata(self, metadata: Dict[str, Any]):
        '''Cleans up level metadata from `self.parent_levels` as well as the given dict, and populates the cleaned data into `self.level_data`.'''
        # Clean up basic level data
        self.level_data.update(metadata)

        for parent_id, parent in self.parent_levels.items():
            remove = []
            for child_id in parent["levels"]:
                # remove levels which point to maps themselves (i.e. don't mark map as "lake-exit: map")
                # as a result of this, every map will have no parent in its name - so it'll just be 
                # something like "chasm" or "center"
                if self.parent_levels.get(child_id) is not None:
                    remove.append(child_id)
            # avoid mutating a dict while iterating over it
            for child_id in remove:
                parent["levels"].pop(child_id)
        for parent_id, parent in self.parent_levels.items():
            for child_id, child in parent["levels"].items():
                self.level_data[child_id]["parent"] = parent["map_id"]
                self.level_data[child_id]["number"] = child["number"]
                self.level_data[child_id]["style"] = child["style"]

        # Clear
        self.parent_levels = {}

        # Saves the level data to leveldata.json
        with open("cache/leveldata.json", "wt") as metadata_file:
            json.dump(self.level_data, metadata_file, indent=3)

    @commands.command()
    @commands.is_owner()
    async def loadmaps(self, ctx):
        '''Loads and renders all levels.
        Initializes the level tree unless otherwise specified.
        Cuts off borders from rendered levels unless otherwise specified.
        '''
        levels = [l[:-2] for l in listdir("data/levels/vanilla") if l.endswith(".l")]

        # Parse and render the level map
        await ctx.send("Loading maps...")
        metadatas = {}
        total = len(levels)
        for i,level in enumerate(levels):
            metadata = self.render_map(
                level,
                source="vanilla", 
                initialize=True, 
                remove_borders=True,
                keep_background=True,
                tile_borders=True
            )
            metadatas[level] = metadata
            await asyncio.sleep(0)
            if i % 50 == 0:
                await ctx.send(f"{i + 1} / {total}")
        await ctx.send(f"{total} / {total} maps loaded.")
        await ctx.send(f"{ctx.author.mention} Done.")

        self.clean_metadata(metadatas)

    def read_objects(self, reader: TextIO) -> int:
        '''Inner function that parses the contents of the data/values.lua file.
        Returns the largest valid object ID for in-level objects.
        '''
        max_id = 0
        rawline = None
        while rawline != "":
            rawline = reader.readline()
            data = rawline.strip()
            # Done parsing, end of the relevant section
            if data == "}":
                break
            
            index = try_index(data, "=")
            # Looking for "key=value" pairs

            # If those are not found, move on
            if len(data) < 2 or index < 0:
                continue
            
            # Since they were found, this means we are now parsing a default object
            item = Item()
            # Determine the object ID of what we're parsing
            data = data[:index].strip()
            o = try_index(data, "object")
            if o == 0:
                temp = 0
                try:
                    temp = int(data[6:])
                    # This will eventually leave us with the largest valid ID
                    if temp and temp > max_id:
                        max_id = temp
                except:
                    pass
            item.obj = data
            
            # Now start parsing the actual data of the object
            raw = None
            while raw != "":
                raw = reader.readline()
                obj = raw.strip()
                # We're done parsing, move on
                if obj == "},":
                    break
                
                # "value=obj" pairs, please
                index = try_index(obj, "=")
                if index == -1: continue
                
                # Isolate the two sides of the equals sign
                value = obj[index + 1: len(obj) - 1].strip()
                obj = obj[: index].strip().lower()
                # Update the previously created Item instance with the data we parsed
                self.set_item_value(item, obj, value)
                
                # ID 0 is special: edge
                if item.ID == 0:
                    item.name = "edge"
                    item.obj = "edge"

            # We're done parsing an object and have escaped the loop above.
            # Now we add the item to out cache.
            self.defaults_by_id[item.ID] = item
            self.defaults_by_object[data] = item
            self.defaults_by_name[item.name] = item

        # We've parsed and stored all objects from data/values.lua in cache.
        # Now we only need to add the special cases:
        # Empty tiles
        empty = Item.empty()
        self.defaults_by_object[empty.obj] = empty
        self.defaults_by_id[empty.ID] = empty
        self.defaults_by_name[empty.name] = empty
        # Level tiles
        level = Item.level()
        self.defaults_by_object[level.obj] = level
        self.defaults_by_id[level.ID] = level
        self.defaults_by_name[level.name] = level
        # The largest valid ID we found
        return max_id

    def set_item_value(self, item: Item, obj: str, value):
        '''Sets an Item's attribute to a value.'''
        # Most of these attributes are commented out.
        # They may be implemented later, if necessary.
        if obj == "name":
            item.name = value[1:len(value) - 1]
        # elif obj == "sprite":
            # item.sprite = value[1:len(value) - 2]
        # elif obj == "sprite_in_root":
            # item.sprite_in_root = int(value)
        # elif obj == "unittype":
            # item.is_object = value == "\"object\""
        # elif obj == "type":
            # item.type = int(value)
        elif obj == "layer":
            item.layer = int(value)
        # elif obj == "colour":
        #     item.color = self.CTS(value, shift=False)
        # # Active should override colour!
        # elif obj == "active":
        #     item.color = self.CTS(value, shift=False)
        # elif obj == "tiling":
            # item.tiling = int(value)
        elif obj == "tile":
            item.ID = self.parse_literal(value)
        # elif obj == "argextra":
            # item.arg_extra = value[1:len(value) - 2].replace("\"", "")
        # elif obj == "argtype":
            # item.arg_type = value[1:len(value) - 2].replace("\"", "")
        # elif obj == "grid":
            # item.grid = self.CTS(value)

    def parse_literal(self, value: str, shift: bool = True) -> int:
        '''Converts a string from the output of data/values.lua to a number.
        Examples:
        "{1}" -> 1
        "{1, 5}" -> 1<<8 | 5 -> 261
        "1" -> 1
        "1, 5" -> 1<<8 | 5 -> 261
        '''
        start_index = 0
        end_index = len(value)
        if try_index(value, "{") == 0:
            start_index += 1
            end_index -= 1
        try:
            index = value.index(",")
        except ValueError:
            return int(value)
        x = int(value[start_index: index - start_index + 1])
        y = int(value[index + 1: end_index].strip())
        if shift:
            return (y << 8) | x
        else:
            return (x, y)

    def read_map(self, filename: str, source: str, data: Optional[TextIO] = None) -> Grid:
        '''Parses a .l file's content, given its file path.
        Returns a Grid object containing the level data.
        '''
        grid = Grid(filename, source)
        if data is None:
            stream = open(grid.fp, "rb")
        else:
            stream = data
        stream.read(28) # don't care about these headers
        buffer = stream.read(2)
        layer_count = int.from_bytes(buffer, byteorder="little")
        # version is assumed to be 261 (it is for all levels as far as I can tell)
        for _ in range(layer_count):
            self.read_layer(stream, grid)
        return grid


    def read_metadata(self, grid: Grid, initialize: bool = False, data: Optional[TextIO] = None, custom: bool = False) -> Grid:
        '''Add everything that's not just basic tile positions & IDs'''
        # We've added the basic objects & their directions. 
        # Now we add everything else:
        if data is None:
            fp = open(grid.fp + "d", errors="replace")
        else:
            fp = data
        
        config = configparser.ConfigParser()
        config.read_file(fp)
        
        # Name and palette should never be missing, but I can't guarantee this for custom levels
        grid.name = config.get("general", "name", fallback="name missing")
        grid.palette = config.get("general", "palette", fallback="default.png")[:-4] # strip .png
        grid.subtitle = config.get("general", "subtitle", fallback=None)
        grid.map_id = config.get("general", "mapid", fallback=None)

        if custom:
            author = config.get("general", "author", fallback="Missing Author")
            # difficulty_string = config.get("general", "difficulty", fallback="")
            # print(difficulty_string)
            grid.extra = author

        # Only applicable to old style levels
        # "cursor not visible" is denoted with X and Y set to -1
        cursor_x = config.getint("general", "selectorX", fallback=-1)
        cursor_y = config.getint("general", "selectorY", fallback=-1)
        if cursor_y != -1 and cursor_x != -1:
            cursor = self.defaults_by_name["cursor"]
            pos = cursor.position = flatten(cursor_x, cursor_y, grid.width)
            grid.cells[pos].append(cursor)

        # Add path objects to the grid (they're not in the normal objects)
        path_count = config.getint("general", "paths", fallback=0)
        for i in range(path_count):
            path = Item()
            pos = flatten(
                config.getint("paths", f"{i}X"),
                config.getint("paths", f"{i}Y"),
                grid.width
            )
            path.position  = pos
            path.direction = config.getint("paths", f"{i}dir")
            path.obj       = config.get("paths", f"{i}object")
            path.ID        = self.defaults_by_object[path.obj].ID
            path.name      = self.defaults_by_object[path.obj].name
            grid.cells[pos].append(path)

        if initialize and grid.map_id is not None:
            # The parent node
            node = {
                "map_id"  : grid.map_id,
                "levels" : {}
            }
            # Key
            parent = grid.filename

        # Add level objects & initialize level tree
        level_count = config.getint("general", "levels", fallback=0)
        for i in range(level_count):
            # Level colors can sometimes be omitted, defaults to white
            color = config.get("levels", f"{i}colour", fallback=None)
            if color is None:
                level = Item.level()
            else:
                level = Item.level(tuple(int(x) for x in color.split(",")))
            
            x = config.getint("levels", f"{i}X") # no fallback
            y = config.getint("levels", f"{i}Y") # if you can't locate it, it's fricked
            pos = flatten(x, y, grid.width)
            level.position = pos
            
            # # z mixed up with layer?
            # z = config.getint("levels", f"{i}Z", fallback=0)
            # level.layer = z

            grid.cells[pos].append(level)

            # level icons: the game handles them as special graphics
            # but the bot treats them as normal objects
            style = config.getint("levels", f"{i}style", fallback=0)
            number = config.getint("levels", f"{i}number", fallback=0)
            name = config.get("levels", f"{i}name", fallback="")
            # "custom" style
            if style == -1:
                icon = Item()
                icon_sprite = config.get("icons", f"{number}file")
                if icon_sprite.startswith("icon"):
                    icon.name = icon_sprite[:-2] # strip _1 for icon sprites
                else:
                    icon.name = icon_sprite[:-4] # strip _0_2 for normal sprites
                # 30 should be above anything else, just a hack
                icon.layer = 30
                grid.cells[pos].append(icon)
            # "dot" style
            elif style == 2 and number >= 10:
                icon = Item()
                icon.name = "icon"
                icon.position = pos
                icon.layer = 30
                grid.cells[pos].append(icon)
            else:
                pass
                # If the bot could be able to draw numbers, letters and
                # dots in the game font (for icons), it would do so here

            if initialize and grid.map_id is not None:
                level_file = config.get("levels", f"{i}file")
                # Each level within
                child = {
                    "number" : number,
                    "name"   : name,
                    "style"  : style
                }
                print("adding norm to node", parent, grid.map_id, level_file, child)
                node["levels"][level_file] = child
        
        # Initialize the level tree
        if initialize and grid.map_id is not None:
            # specials are only used for special levels at the moment
            special_count = config.getint("general", "specials", fallback=0)
            for i in range(special_count):
                special_data = config.get("specials", f"{i}data")
                special_kind, *special_rest = special_data.split(",")
                if special_kind == "level":
                    # note: because of the comma separation these are still strings
                    level_file, style, number, *_ = special_rest
                    child = {
                        "number" : int(number),
                        "name"   : None,
                        "style"  : int(style)
                    }
                    print("adding spec to node", parent, grid.map_id, level_file, child)
                    node["levels"][level_file] = child
                
            # merges both normal level & special level data together
            if node["levels"]:
                self.parent_levels[parent] = node

        # Add background images
        image_count = config.getint("images", "total", fallback=0)
        for i in range(image_count):
            grid.images.append(config.get("images", str(i)))
        
        # Alternate would be to use changed_count & reading each record
        # The reason these aren't all just in `changed` is that MF2 limits
        # string sizes to 1000 chars or so.
        #
        # TODO: is it possible for `changed_short` to go over 1000 chars?
        # Probably not, since you'd need over 300 changed objects and I'm
        # not sure that's allowed by the editor (maybe file editing)
        #
        # `changed_short` exists for some custom levels
        changed_record = config.get("tiles", "changed_short", fallback=None)
        if changed_record is None:
            # levels in the base game (and custom levels without `changed_short`)
            # all provide `changed`, which CAN be an empty string
            # `split` doesn't filter out the empty string so this 
            changed_record = config.get("tiles", "changed")
            changed_tiles = [x for x in changed_record.rstrip(",").split(",") if x != ""]
        else:
            changed_tiles = [f"object{x}" for x in changed_record.rstrip(",").split(",") if x != ""]
        
        # include only changes that will affect the visuals
        changes = {tile: {} for tile in changed_tiles}
        attrs = ("name", "image", "colour", "activecolour", "layer")
        for tile in changed_tiles:
            for attr in attrs:
                # `tile` is of the form "objectXYZ", and 
                new_attr = config.get("tiles", f"{tile}_{attr}", fallback=None)
                if new_attr is not None:
                    changes[tile][attr] = new_attr
        
        for cell in grid.cells:
            for item in cell:
                if item.obj in changes:
                    change = changes[item.obj]
                    if "name" in change:
                        if change["name"] in self.bot.get_cog("Admin").tile_data:
                            item.name = change["name"]
                        else:
                            item.name = "default"
                    # The sprite overrides the name in this case
                    if "image" in change:
                        if change["image"] in self.bot.get_cog("Admin").tile_data:
                            item.name = change["image"]
                        else:
                            item.name = "default"
                    if "layer" in change:
                        item.layer = int(change["layer"])
                    # Text tiles always use their active color in renders,
                    # so `activecolour` is preferred over `colour`
                    #
                    # Including both active and inactive tiles would require
                    # the bot to parse the rules of the level, which is a 
                    # lot of work for very little
                    #
                    # This unfortunately means that custom levels that use drastically
                    # different active & inactive colors will look different in renders
                    if "colour" in change:
                        item.color = tuple(int(x) for x in change["colour"].split(","))
                    if "activecolour" in change and item.name.startswith("text_"):
                        item.color = tuple(int(x) for x in change["activecolour"].split(","))

        # Makes sure objects within a single cell are rendered in the right order
        # Items are sorted according to their layer attribute, in ascending order.
        for cell in grid.cells:
            cell.sort(key=lambda x: x.layer)
        
        return grid
        
    def read_layer(self, stream: io.BytesIO, grid: Grid):
        buffer = stream.read(4)
        grid.width = int.from_bytes(buffer, byteorder="little")
        
        buffer = stream.read(4)
        grid.height = int.from_bytes(buffer, byteorder="little")
        
        size = grid.width * grid.height
        if size > 10_000:
            raise Exception("oh frick")
        if len(grid.cells) == 0:
            for _ in range(size):
                grid.cells.append([])
        
        stream.read(32) # don't care about these

        data_blocks = int.from_bytes(stream.read(1), byteorder="little")

        # MAIN
        stream.read(4)
        buffer = stream.read(4)
        compressed_size = int.from_bytes(buffer, byteorder="little")
        compressed = stream.read(compressed_size)

        zobj = zlib.decompressobj()
        map_buffer = zobj.decompress(compressed)

        items = []
        for j,k in enumerate(range(0, len(map_buffer), 2)):
            cell = grid.cells[j]
            ID = int.from_bytes(map_buffer[k : k + 2], byteorder="little")

            item = self.defaults_by_id.get(ID)
            if item is not None:
                item = item.copy()
            else:
                item = Item.empty()
                ID = -1
            item.position = j
            items.append(item)
            
            if ID != -1:
                cell.append(item)

        if data_blocks == 2:
            # DATA
            stream.read(9)
            buffer = stream.read(4)
            compressed_size = int.from_bytes(buffer, byteorder="little") & (2**32 - 1)

            zobj = zlib.decompressobj()
            dirs_buffer = zobj.decompress(stream.read(compressed_size))

            for j in range(len(dirs_buffer) - 1):
                item = items[j]
                item.direction = dirs_buffer[j]
        
    @tasks.loop(minutes=15)
    async def update_custom_levels(self):
        with open("cache/customlevels.json", "w") as f:
            json.dump(self.custom_levels, f)

def setup(bot: commands.Bot):
    bot.add_cog(Reader(bot))