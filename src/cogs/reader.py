import asyncio
import discord
import json
import zlib

from discord.ext import commands
from functools   import partial
from os          import listdir, stat
from src.utils   import Tile

def flatten(x, y, width):
    '''Return the flattened position of a coordinate in a grid of specified width'''
    return int(y) * width + int(x)

def try_index(string, value):
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
    def __init__(self, filename, source):
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
        self.images = []
        # Object information
        self.width = 0
        self.height = 0
        self.cells = []
        # Parent level and map identification
        self.parent = None
        self.map_id = None
        self.style = None
        self.number = None
    
    def clean_up(self):
        '''Returns a cleaned up version of the grid.'''
        # Horrible variable naming scheme below
        grid = []
        h = self.height
        w = self.width
        for y in range(h):
            a = []
            for x in range(w):
                z = []
                for o in self.cells[y * w + x].objects:
                    # Cleaned up Item object
                    new = f"{o.name or 'error'}:{'0' if o.direction is None else str(o.direction * 8)}{':' + ','.join(tuple(map(str,o.color))) if o.color else ''}" 
                    z.append(new)
                a.append(z)
            grid.append(a)
        # Handle level images as well
        final = {
            "objects" : grid,
            "data" : {
                "images"     : self.images,
                "palette"    : self.palette,
                "name"       : self.name,
                "subtitle"   : self.subtitle,
                "mapID"      : self.map_id,
                "parent"     : self.parent,
                "width"      : self.width,
                "height"     : self.height,
                "source"     : self.source,
                "filename"   : self.filename,
                "number"     : self.number,
                "style"      : self.style
            }
        }
        return final

class Cell:
    '''Contains the information stored in a single position of a level. 
    Not really necessary.
    '''
    def __init__(self):
        '''Initializes a blank cell.'''
        self.objects = []

class Item:
    '''Represents an object within a level.
    This may be a regular object, a path object, a level object, a special object or empty.
    '''
    def __init__(self, *, ID=None, obj=None, name=None, color=None, position=None, direction=None, extra=None, layer=0):
        '''Returns an Item with the given parameters.'''
        self.ID = ID
        self.obj = obj
        self.name = name
        self.color = color or None
        self.position = position
        self.direction = direction
        self.extra = extra
        self.layer = layer

    def copy(self):
        '''Returns a copy of the item.'''
        return Item(ID=self.ID, obj=self.obj, name=self.name, color=self.color, position=self.position, direction=self.direction, extra=self.extra, layer=self.layer)

    @classmethod
    def edge(cls):
        '''Returns an Item representing an edge tile.'''
        return Item(ID=0, obj="edge", name="edge", layer=20)
    
    @classmethod
    def empty(cls):
        '''Returns an Item representing an empty tile.'''
        return Item(ID=-1, obj="empty", name="empty", layer=0)
    
    @classmethod
    def level(cls, color=(0,3)):
        '''Returns an Item representing a level object.'''
        return Item(ID=-2, obj="level", name="level", color=color, layer=20)

class Reader(commands.Cog, command_attrs=dict(hidden=True)):
    '''A class for parsing the contents of level files.'''
    def __init__(self, bot):
        '''Initializes the Reader cog.
        Populates the default objects cache from a data/values.lua file.
        '''
        self.bot = bot
        self.defaults_by_id = {}
        self.defaults_by_object = {}
        self.defaults_by_name = {}
        self.level_data = {}
        # Intermediary, please don't access
        self._levels = {}

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

    def render_map(
        self, 
        filename, 
        source, 
        initialize=False, 
        tile_data=None, 
        renderer=None, 
        remove_borders=False, 
        keep_background=False, 
        tile_borders=False
    ):
        '''Loads and renders a level, given its file path and source. 
        Shaves off the borders if specified.
        '''
        # Data
        grid = self.read_map(filename, source=source, initialize=initialize)

        # Clean up the grid
        m = grid.clean_up()
        images = m["data"]["images"]
        palette = m["data"]["palette"]
        source = m["data"]["source"]
        width = m["data"]["width"]
        height = m["data"]["height"]
        filename = m["data"]["filename"]
        out = f"target/renders/{source}/{filename}.gif"

        # Shave off the borders:
        if remove_borders:
            # First and last rows
            m["objects"].pop(height - 1)
            m["objects"].pop(0)
            # First and last columns of each row
            for row in m["objects"]:
                row.pop(width - 1)
                row.pop(0)

        # Handle sprite variants
        tiles = renderer.handle_variants(m["objects"], tile_borders=tile_borders, is_level=True)

        # (0,4) is the color index for level backgrounds
        background = (0,4) if keep_background else None

        # Render the level
        renderer.magick_images(tiles, width, height, palette=palette, images=images, image_source=source, background=background, out=out)
        
        # Return level metadata
        return {grid.filename: m["data"]}

    def pre_map_load(self):
        '''Prerequisites for level rendering'''
        tile_data = self.bot.get_cog("Admin").tile_data
        # If the objects for some reason aren't well formed, they're replaced with error tiles
        renderer = self.bot.get_cog("Baba Is You")
        return tile_data, renderer

    @commands.command()
    @commands.is_owner()
    async def loadmap(self, ctx, source, filename, initialize: bool =False):
        '''Loads a given level. Initializes the level tree if so specified.'''
        # For managing the directions of the items
        tile_data, renderer = self.pre_map_load()
        # Parse and render
        metadata = self.render_map(
            filename, 
            source=source, 
            tile_data=tile_data, 
            renderer=renderer, 
            initialize=initialize, 
            remove_borders=True,
            keep_background=True,
            tile_borders=True
        )
        # This should mostly just be false
        if initialize:
            self.clean_metadata(metadata)
        await ctx.send(f"Rendered level at `{source}/{filename}`.")

    def clean_metadata(self, metadata):
        '''Cleans up level metadata from self._levels as well as the given dict, and populates the cleaned data into self.level_data.'''
        # Clean up basic level data
        for level,data in metadata.items():
            self.level_data[level] = data

        # Clean up level parents
        for children in self._levels.values():
            remove = []
            for child in children["levels"]:
                if self._levels.get(child) is not None:
                    remove.append(child)
            for child in remove:
                children["levels"].pop(child)
        for children in self._levels.values():
            for child in children["levels"]:
                self.level_data[child]["parent"] = children["mapID"]
                self.level_data[child]["number"] = children["levels"][child]["number"]
                self.level_data[child]["style"] = children["levels"][child]["style"]

        # Clear
        self._levels = {}

        # Saves the level data to leveldata.json
        with open("cache/leveldata.json", "wt") as metadata_file:
            json.dump(self.level_data, metadata_file, indent=3)

    @commands.command()
    @commands.is_owner()
    async def loadmaps(self, ctx, initialize=True, remove_borders=True):
        '''Loads and renders all levels.
        Initializes the level tree unless otherwise specified.
        Cuts off borders from rendered levels unless otherwise specified.
        '''
        levels = [l[:-2] for l in listdir("data/levels/vanilla") if l.endswith(".l")]

        # For managing the directions of the items
        tile_data, renderer = self.pre_map_load()

        # Parse and render the level map
        await ctx.send("Loading maps...")
        metadatas = {}
        total = len(levels)
        for i,level in enumerate(levels):
            # Band-aid to patch weird crashy levels
            if level in ("0level", "80level"): continue
            try:
                metadata = self.render_map(
                    level, source="vanilla", 
                    tile_data=tile_data, 
                    renderer=renderer, 
                    initialize=True, 
                    remove_borders=True,
                    keep_background=True,
                    tile_borders=True
                    )
            except zlib.error as e:
                print(level)
            else:
                metadatas.update(metadata)
                if i % 50 == 0:
                    await ctx.send(f"{i + 1} / {total}")
            finally:
                await asyncio.sleep(0)
        await ctx.send(f"{total} / {total} maps loaded.")
        await ctx.send(f"{ctx.author.mention} Done.")

        self.clean_metadata(metadatas)

    def read_objects(self, reader):
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

    def set_item_value(self, item, obj, value):
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
            item.ID = self.CTS(value)
        # elif obj == "argextra":
            # item.arg_extra = value[1:len(value) - 2].replace("\"", "")
        # elif obj == "argtype":
            # item.arg_type = value[1:len(value) - 2].replace("\"", "")
        # elif obj == "grid":
            # item.grid = self.CTS(value)

    def CTS(self, value, shift=True):
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

    def read_map(self, filename, source, initialize = False):
        '''Parses a .l file's content, given its file path.
        Returns a Grid object containing the level data.
        '''
        grid = Grid(filename, source)
        with open(grid.fp, "rb") as stream:
            header = int.from_bytes(stream.read(8), byteorder="little") & (2**64 - 1)
            # ACHTUNG
            assert header == 0x21474e5554484341
            version = int.from_bytes(stream.read(2), byteorder="little") & (2**16 - 1)
            assert version >= 256 and version <= 261
            
            buffer = None
            while buffer != 0:
                data = stream.read(8)
                buffer = int.from_bytes(data, byteorder="little") & (2**32 - 1)
                # MAP
                if buffer == 0x2050414d:
                    stream.read(2)
                # LAYR
                elif buffer == 0x5259414c:
                    buffer = stream.read(2)
                    # The layer count
                    layer_count = int.from_bytes(buffer, byteorder="little") & (2**16 - 1)
                    # Mysterious off-by-one magic
                    for _ in range(layer_count + 1):
                        self.read_layer(stream, grid, version)
                    break

        # We've added the basic objects & their directions. 
        # Now we add everything else:
        with open(grid.fp + "d", errors="replace") as fp:
            # Paths
            grid = self.add_paths(grid, file=fp)
            # Levels
            grid = self.add_levels(grid, file=fp, initialize=initialize) # If we want to also initialize the level tree
            # Images
            grid = self.add_images(grid, file=fp)
            # Level metadata (must be below add_specials)
            grid = self.add_metadata(grid, file=fp)
            # Special objects
            grid = self.add_specials(grid, file=fp, initialize=initialize)
            # Object changes
            grid = self.add_changes(grid, file=fp)

        # Makes sure objects within a single cell are rendered in the right order
        grid = self.sort_layers(grid)
        
        return grid

    def sort_layers(self, grid):
        '''Sorts the items within each cell of the grid.
        Items are sorted according to their layer attribute, in ascending order.
        '''
        for cell in grid.cells:
            cell.objects.sort(key=lambda x: x.layer)

        return grid

    def add_changes(self, grid, file):
        '''Modifies the objects in the level according to the changes proposed in the given file.'''
        # the .ld file
        file.seek(0)
        changes = {}

        # Go through each line of the file
        raw = None
        while raw != "":
            raw = file.readline()
            line = raw.strip()
            
            # We're starting parsing the object changes section
            if line == "[tiles]":
                rawl = None
                while rawl != "":
                    rawl = file.readline()
                    data = rawl.strip()

                    # Which objects are changed?
                    if data.startswith("changed="):
                        changes = dict.fromkeys(line[8:].split(","), None)
                        continue
                    
                    # We're done parsing
                    # We've exited [tiles] and entered a new "group"
                    if data.startswith("["):
                        break

                    # Parsing
                    index = try_index(data, "=")
                    if index == -1: continue

                    # These are the bits of information we care about
                    values = ["_name", "_image", "_colour", "_activecolour"]
                    for v in values:
                        param_index = try_index(data, v)
                        if param_index != -1:
                            break
                        # Don't need the line anymore, move on
                    if param_index == -1:
                        continue
                    
                    # This will be an element of `values`
                    param = data[param_index:index]

                    # The object ID prefixing the line
                    key = data[:param_index]
                    if changes.get(key) is None:
                        changes[key] = {}
                    changes[key][param] = data[index + 1:]
        
        # Updates the grid:
        # The name and color are updated.
        if changes:
            for cell in grid.cells:
                for item in cell.objects:
                    new = changes.get(item.obj)
                    if new is not None:
                        if new.get("_name") is not None:
                            item.name = new["_name"]
                        elif new.get("_image") is not None:
                            item.name = new["_image"]
                        if new.get("_activecolour") is not None and item.name.startswith("text_"):
                            item.color = [int(new["_activecolour"][0]), int(new["_activecolour"][2])]
                        elif new.get("_colour") is not None:
                            item.color = [int(new["_colour"][0]), int(new["_colour"][2])]

        
        return grid

    def add_metadata(self, grid, file):
        '''Adds level metadata from the given file to the given Grid.
        Adds the following information:
        * Level name 
        * Subtitle
        * Palette
        * Cursor position
        '''
        # Our data
        name = subtitle = palette = cursor_x = cursor_y = map_id = None
        file.seek(0)
        # Go through each line of the file
        line = None
        while line != "":
            line = file.readline().strip()
            # Level name
            if line.startswith("name="):
                name = line[5:]
            # Palette (strip .png)
            if line.startswith("palette="):
                palette = line[8:-4]
            # Level subtitle
            if line.startswith("subtitle="):
                subtitle = line[9:]
            # Custom level parent
            if line.startswith("mapid="):
                map_id = line[6:]
            # Cursor position
            if line.startswith("selectorX="):
                pos = line[10:]
                if pos != -1:
                    cursor_x = int(pos)
            if line.startswith("selectorY="):
                pos = line[10:]
                if pos != -1:
                    cursor_y = int(pos)
        # Add cursor
        if cursor_x is not None and cursor_y is not None:
            cursor_position = flatten(cursor_x, cursor_y, grid.width)
            grid.cells[cursor_position].objects.append(self.defaults_by_name["cursor"])

        # Apply level data
        grid.name = name
        grid.subtitle = subtitle
        # Palette
        if palette is None:
            grid.palette = "default"
        else:
            grid.palette = palette
        # Personal map ID
        if map_id is not None:
            grid.map_id = map_id

        return grid

    def add_levels(self, grid, file, initialize=False):
        '''Adds raw level objects from within a level to the given Grid.
        Data is parsed from the given file.
        if `initialize` is True, adds levels to the global level tree.
        '''
        file.seek(0)
        levels = {}
        icons = {}
        level_count = 0
        map_id = ""
        # Go through each line of the file
        line = None
        while line != "":
            line = file.readline().strip()
            # How many levels are there in the map??
            if line.startswith("levels="):
                level_count = int(line[7:])
            # When initializing the level tree:
            if initialize and line.startswith("mapid="):
                map_id = line[6:]
            
            # We're starting parsing levels
            if line == "[levels]":
                data = None
                while data != "":
                    data = file.readline().strip()
                    
                    # We're done parsing
                    # We've exited [levels] and entered a new "group"
                    if data.startswith("["):
                        break
                    
                    # not what we're looking for
                    if not data[:1].isnumeric():
                        continue

                    # Parsing
                    index = data.index("=")

                    # These are the bits of information we care about
                    if initialize:
                        values = ["X", "Y", "style", "colour", "number", "file", "name"]
                    else:
                        values = ["X", "Y", "style", "colour", "number"]
                    for v in values:
                        param_index = try_index(data, v)
                        if param_index != -1:
                            break
                        # Don't need the line anymore, move on
                    if param_index == -1:
                        continue
                    
                    # This will be an element of `values`
                    param = data[param_index:index]

                    # The number prefixing the line
                    key = data[:param_index]
                    if key.isnumeric():
                        # Ignore levels with IDs above the levelcount
                        # Because those are not actual levels???
                        if int(key) <= level_count - 1:
                            # If the level is new
                            if levels.get(key) is None:
                                levels[key] = {}
                            # Store the level data
                            levels[key][param] = data[index + 1:]
                
            # We're starting parsing level icons
            if line == "[icons]":
                data = None
                while data != "":
                    data = file.readline().strip()
                    
                    # We're done parsing
                    # We've exited [icons] and entered a new "group"
                    if data.startswith("["):
                        break
                    
                    # not what we're looking for
                    if not data[:1].isnumeric():
                        continue

                    # Parsing
                    index = data.index("=")

                    # These are the bits of information we care about
                    values = ["file"]
                    for v in values:
                        param_index = try_index(data, v)
                        if param_index != -1:
                            break
                        # Don't need the line anymore, move on
                    if param_index == -1:
                        continue
                    
                    param = "file"

                    # The number prefixing the line
                    key = data[:param_index]
                    if key.isnumeric():
                        # Ignore levels with IDs above the levelcount
                        # Because those are not visible when playing the game
                        if int(key) <= level_count - 1:
                            # If the level icon is new
                            if icons.get(key) is None:
                                icons[key] = {}
                            # Store the level icon
                            icons[key][param] = data[index + 1:]

        # Update our grid object with the levels
        for data in levels.values():
            # Level position
            position = flatten(data["X"], data["Y"], grid.width)

            # Level color
            if data.get("colour") is not None:
                color = (int(data["colour"][0]), int(data["colour"][2]))
                level = Item.level(color=color)
            else:
                level = Item.level()

            # Level objects can be any color
            level.position = position

            # Levels are (sort of) like any other object
            grid.cells[position].objects.append(level)
            # Levels that use custom icons:
            if data["style"] == "-1":
                # The number of the level is the icon key
                number = data["number"]
                icon_file = icons[number]["file"]

                icon = Item()
                icon.position = position
                # This is a hack to work around the fact that 
                    # This is a hack to work around the fact that 
                # This is a hack to work around the fact that 
                    # This is a hack to work around the fact that 
                # This is a hack to work around the fact that 
                    # This is a hack to work around the fact that 
                # This is a hack to work around the fact that 
                    # This is a hack to work around the fact that 
                # This is a hack to work around the fact that 
                    # This is a hack to work around the fact that 
                # This is a hack to work around the fact that 
                # the game does not consider level icons objects, but 
                # our rendering framework does:
                # Remove _1 from the file name if
                if icon_file.startswith("icon"):
                    icon.name = icon_file[:-2]
                else:
                    icon.name = icon_file[:-4]
                # Bring to the front layer whenever possible
                icon.layer = 30
                grid.cells[position].objects.append(icon)
            # Levels using the dot icons + the default level icon
            elif data["style"] == "2":
                icon = Item()
                icon.position = position
                # This is a hack to work around the fact that 
                    # This is a hack to work around the fact that 
                # This is a hack to work around the fact that 
                    # This is a hack to work around the fact that 
                # This is a hack to work around the fact that 
                    # This is a hack to work around the fact that 
                # This is a hack to work around the fact that 
                    # This is a hack to work around the fact that 
                # This is a hack to work around the fact that 
                    # This is a hack to work around the fact that 
                # This is a hack to work around the fact that 
                # the game does not consider level icons objects, but 
                # our rendering framework does:
                # Create an item with the name "icon"
                icon.name = "icon"
                # Bring to the front layer whenever possible
                icon.layer = 30
                grid.cells[position].objects.append(icon)

            # Handle the level tree
            if initialize:
                # The parent node
                node = {
                    "mapID"  : map_id,
                    "levels" : {}
                }
                # Key
                parent = grid.filename
                # Each level within
                for l in levels.values():
                    child = {
                        "number" : l["number"],
                        "name"   : l["name"],
                        "style"  : l["style"]
                    }
                    # nice nested level ids
                    node["levels"][l["file"]] = child
                                            
                self._levels[parent] = node
        
        return grid
    
    def add_paths(self, grid, file):
        '''Adds raw path objects from within a level to the given Grid.
        Objects are added to the Grid as regular objects without path information.
        Data is parsed from the given file.
        '''
        file.seek(0)
        paths = {}
        path_count = 0

        # Go through each line of the file
        line = None
        while line != "": 
            line = file.readline().strip()                
            # How many path objects are there in the map?
            if line.startswith("paths="):
                path_count = int(line[6:])
            
            # We've started parsing paths
            if line == "[paths]":
                data = None
                while data != "":
                    data = file.readline().strip()
                    
                    # We're done parsing
                    # "[paths]" section is over
                    # new section has started
                    if data.startswith("["):
                        break
                    
                    # not what we're looking for
                    if not data[:1].isnumeric():
                        continue

                    # Parsing
                    index = data.index("=")
                    # These are the bits of information we care about
                    values = ["X", "Y", "object", "dir"]
                    for v in values:
                        param_index = try_index(data, v)
                        if param_index != -1:
                            break
                    if param_index == -1:
                        continue

                    # This will be "X", "Y", "object" or "dir"
                    param = data[param_index:index]

                    # The number prefixing the line
                    key = data[:param_index]
                    if key.isnumeric():
                        # Ignore paths with IDs above the pathcount
                        # Because those are not actual paths???
                        if int(key) <= path_count - 1:
                            # If the path is new
                            if paths.get(key) is None:
                                paths[key] = {}
                            # Store the path position, dir & object
                            paths[key][param] = data[index + 1:]

        # Update our grid object with the levels
        for data in paths.values():
            path = Item()
            position = flatten(data["X"], data["Y"], grid.width)

            path.position  = position
            path.direction = int(data["dir"])
            path.obj       = data["object"]
            path.ID        = self.defaults_by_object[data["object"]].ID
            path.name      = self.defaults_by_object[data["object"]].name
            # Paths are (sort of) like any other object
            grid.cells[position].objects.append(path)
        
        
        return grid

    def add_images(self, grid, file):
        '''Adds background image data from a level to the given Grid.
        Data is parsed from the given file.
        '''
        # The .ld file
        file.seek(0)
        images = {}

        # Go through each line of the file
        line = None
        while line != "":
            line = file.readline().strip()            
            # This is where we begin parsing
            if line == "[images]":
                data = None
                while data != "":
                    data = file.readline().strip()
                    
                    # We're done parsing
                    # The "[images]" section is over and
                    # A new section has begun
                    if data.startswith("["):
                        break
                    
                    # not what we're looking for
                    if not data[0].isnumeric():
                        continue

                    # Parsing
                    index = data.index("=")
                    # This dictates the order of the images
                    # Lower key -> lower Z position
                    key = data[:index]
                    value = data[index + 1:]
                    
                    # Store this
                    images[key] = value

        # Convert to list 
        sorted_images = dict(sorted(images.items(), key=lambda x: int(x[0])))
        sorted_list = [s for s in sorted_images.values()]
        # Update our grid
        grid.images = sorted_list
        return grid

    def add_specials(self, grid, file, initialize=False):
        '''Adds special objects from within a level to the given Grid.
        Data is parsed from the given file.
        '''
        # the .ld file
        file.seek(0)
        specials = {}
        special_count = 0
        map_id = ""
        # Go through each line of the file
        line = None
        while line != "":
            line = file.readline().strip()                
            # How many speicl objects are there in the map?
            if line.startswith("specials="):
                special_count = int(line[9:])
            # When initializing the level tree:
            if initialize and line.startswith("mapid="):
                map_id = line[6:]
            
            # We've started parsing paths
            if line == "[specials]":
                data = None
                while data != "":
                    data = file.readline().strip()
                    
                    # We're done parsing
                    # "[specials]" section is over
                    # new section has started
                    if data.startswith("["):
                        break

                    # not what we're looking for
                    if not data[:1].isnumeric():
                        continue

                    # Parsing
                    index = data.index("=")
                    # These are the bits of information we care about
                    values = ["X", "Y", "data"]
                    for v in values:
                        param_index = try_index(data, v)
                        if param_index != -1:
                            break
                    if param_index == -1:
                        continue
                    
                    # This will be "X", or "Y" or "data"
                    param = data[param_index:index]

                    # The number prefixing the line
                    key = data[:param_index]
                    if key.isnumeric():
                        # Ignore specials with IDs above the pathcount
                        # Because those are not actual specials???
                        if int(key) <= special_count - 1:
                            # If the special is new
                            if specials.get(key) is None:
                                specials[key] = {}
                            # Store the special position & data
                            specials[key][param] = data[index + 1:]
    
        # Handle the actual special information
        for special in specials.values():
            split = special["data"].split(",") 
            if split[0] == "level":
                position = flatten(special["X"], special["Y"], grid.width)
                level = Item.level()
                level.position = position
                # grid.cells[position].objects.append(level)

                # Handle the level tree
                if initialize:
                    # The parent node
                    map_id = grid.map_id
                    for parent_id,children in self._levels.items():
                        if children.get("mapID") == map_id:
                            parent = parent_id
                    
                    # Relevant fields
                    level_id = split[1]
                    style = split[2]
                    number = split[3]
                                                
                    self._levels[parent]["levels"][level_id] = {
                        "number" : number,
                        "style"  : style,
                        "name"   : None
                    }

        return grid
            
    def read_layer(self, stream, grid, version):
        buffer = stream.read(4)
        
        if buffer == b"":
            return

        grid.width = int.from_bytes(buffer, byteorder="little") & (2**32 - 1)
        
        buffer = stream.read(4)
        grid.height = int.from_bytes(buffer, byteorder="little") & (2**32 - 1)

        if version >= 258:
            stream.read(4)
        stream.read(25)

        if version == 260:
            stream.read(2)
        elif version == 261:
            stream.read(3)
        
        size = grid.width * grid.height
        if len(grid.cells) == 0:
            for _ in range(size):
                grid.cells.append(Cell())

        data_blocks = int.from_bytes(stream.read(1), byteorder="little") & (2**8 - 1)
        assert not (data_blocks < 1 and data_blocks > 2)

        # MAIN
        stream.read(4)
        buffer = stream.read(4)
        compressed_size = int.from_bytes(buffer, byteorder="little") & (2**32 - 1)
        next_position = stream.tell() + compressed_size

        zobj = zlib.decompressobj()
        map_buffer = zobj.decompress(stream.read(size * 2))
        read = len(map_buffer)
        
        read >>= 1
        

        stream.seek(next_position)

        items = []
        for j,k in zip(range(read), range(0, 2 * read, 2)):
            cell = grid.cells[j]
            ID = int.from_bytes(map_buffer[k : k + 16], byteorder="little") & (2**16 - 1)

            item = self.defaults_by_id.get(ID)
            if item is not None:
                item = item.copy()
            else:
                item = Item.empty()
                ID = -1
            item.position = j
            items.append(item)
            
            if ID != -1:
                cell.objects.append(item)

        if data_blocks == 2:
            # DATA
            map_buffer = stream.read(13)
            compressed_size = int.from_bytes(map_buffer[9:], byteorder="little") & (2**32 - 1)
            next_position = stream.tell() + compressed_size

            zobj = zlib.decompressobj()
            map_buffer = zobj.decompress(stream.read(size))
            read = len(map_buffer)

            stream.seek(next_position)

            for j in range(read):
                item = items[j]
                item.direction = map_buffer[j]

def setup(bot):
    bot.add_cog(Reader(bot))