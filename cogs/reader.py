import discord
import json
import zlib

from discord.ext import commands
from os          import listdir, stat

def flatten(x, y, width):
    '''
    Return the flattened position of a coordinate in a grid of specified width
    '''
    return int(y) * width + int(x)

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

class Grid:
    '''
    This stores the information of a single Baba level, in a format readable by the renderer.
    '''
    def __init__(self, filename, source):
        '''
        Initializes a blank grid, given a path to the level file. 
        This should not be used; you should use Reader.readMap() instead to generate a filled grid.
        '''
        self.images = []
        self.name = ""
        self.parent = ""
        self.subtitle = ""
        self.palette = ""
        self.width = 0
        self.height = 0
        self.cells = []
        self.fp = f"levels/{source}/{filename}.l"
        self.filename = filename
        self.source = source
    
    def serialize(self):
        '''
        Returns a json-serialized version of the grid. Used for debugging purposes.
        '''
        # Horrible variable naming scheme below
        m = []
        h = self.height
        w = self.width
        for y in range(h):
            a = []
            for x in range(w):
                z = []
                for o in self.cells[y * w + x].objects:
                    # From Item object to json object / dict
                    new = {
                        "ID"        : o.ID,
                        "obj"       : o.obj,
                        "name"      : o.name,
                        "position"  : o.position,
                        "direction" : 0 if o.direction is None else o.direction,
                        "extra"     : "" if o.extra is None else o.extra
                    }
                    z.append(new)
                a.append(z)
            m.append(a)
        # Handle level images as well
        final = {
            "objects" : m,
            "data" : {
                "images"   : self.images,
                "palette"  : self.palette,
                "name"     : self.name,
                "subtitle" : self.subtitle,
                "parent"   : self.parent,
                "width"    : self.width,
                "height"   : self.height,
                "source"   : self.source,
                "filename" : self.filename
            }
        }
        return final

class Cell:
    '''
    Contains the information stored in a single position of a level. 
    Not really necessary.
    '''
    def __init__(self):
        '''
        Initializes a blank cell.
        '''
        self.objects = []

class Item:
    '''
    Represents an object within a level.
    This may be a regular object, a path object, a level object, a special object or empty.
    '''
    def __init__(self, *, ID=None, obj=None, name=None, position=None, direction=None, extra=None, layer=0):
        '''
        Returns an Item with the given parameters.
        '''
        self.ID = ID
        self.obj = obj
        self.name = name
        self.position = position
        self.direction = direction
        self.extra = extra
        self.layer = layer

    def copy(self):
        '''
        Returns a copy of the item.
        '''
        return Item(ID=self.ID, obj=self.obj, name=self.name, position=self.position, direction=self.direction, extra=self.extra, layer=self.layer)

    @classmethod
    def edge(cls):
        '''
        Returns an Item representing an edge tile.
        '''
        return Item(ID=0, obj="edge", name="edge", layer=20)
    
    @classmethod
    def empty(cls):
        '''
        Returns an Item representing an empty tile.
        '''
        return Item(ID=-1, obj="empty", name="empty", layer=0)
    
    @classmethod
    def level(cls):
        '''
        Returns an Item representing a level object.
        '''
        return Item(ID=-2, obj="level", name="level", layer=20)

class Reader(commands.Cog, command_attrs=dict(hidden=True)):
    '''
    A class for parsing the contents of level files.
    '''
    def __init__(self, bot):
        '''
        Initializes the Reader cog.
        Populates the default objects cache from a "values.lua" file.
        '''
        self.bot = bot
        self.defaultsById = {}
        self.defaultsByObject = {}
        self.defaultsByName = {}
        self.levelData = {}
        # Intermediary, please don't access
        self._levels = {}

        with open("values.lua") as reader:
            line = None
            while line != "":
                line = reader.readline()
                index = tryIndex(line, "tileslist =")
                if index == -1:
                    continue
                elif index == 0:
                    # Parsing begins
                    self.readObjects(reader)
                    break
        
        # Level data cache
        levelcache = "cache/leveldata.json"
        if stat(levelcache).st_size != 0:
            self.levelData = json.load(open(levelcache))

    async def renderMap(self, filename, source, initialize=False, dirs=None, renderer=None, removeBorders=False):
        '''
        Loads and renders a level, given its file path and source. 
        Shaves off the borders if specified.
        '''
        # Data
        grid = await self.readMap(filename, source=source, initialize=initialize)

        # Serialize the grid
        m = grid.serialize()
        images = m["data"]["images"]
        palette = m["data"]["palette"]
        source = m["data"]["source"]
        width = m["data"]["width"]
        height = m["data"]["height"]
        filename = m["data"]["filename"]
        out = f"renders/{source}/{filename}.gif"

        # Shave off the borders:
        if removeBorders:
            # First and last rows
            m["objects"].pop(height - 1)
            m["objects"].pop(0)
            # First and last columns of each row
            for row in m["objects"]:
                row.pop(width - 1)
                row.pop(0)

        # Handle sprite variants
        tiles = [[[f'{obj["name"]}:{dirs(obj)}' for obj in cell] for cell in row] for row in m["objects"]]
        tiles = renderer.handleVariants(tiles)

        # Render the level
        renderer.magickImages(tiles, width, height, images=images, palette=palette, imageSource=source, out=out)
    
    @commands.command()
    @commands.is_owner()
    async def loadmap(self, ctx, source, filename, initialize: bool =False):
        '''
        Loads a given level. Initializes the level tree if so specified.
        '''
        # For managing the directions of the items
        tileData = self.bot.get_cog("Admin").tileColors
        dirs = lambda o: o["direction"] * 8 if tileData[o["name"]]["tiling"] in ["0","2","3"] else 0
        renderer = self.bot.get_cog("Baba Is You")
        # Parse and render
        await self.renderMap(filename, source=source, dirs=dirs, renderer=renderer, initialize=initialize, removeBorders=True)
        # This should mostly just be false
        if initialize:
            self.cleanMetadata()
        await ctx.send(f"Rendered level at `{source}/{filename}`.")

    def cleanMetadata(self):
        '''
        Cleans up level metadata from self._levels, and populates the cleaned data into self.levelData.
        '''
        # Clean up level metadata 
        for children in self._levels.values():
            remove = []
            for child in children["levels"]:
                if self._levels.get(child) is not None:
                    remove.append(child)
            for child in remove:
                children["levels"].pop(child)
        self.levelData = self._levels
        self._levels = {}

    @commands.command()
    @commands.is_owner()
    async def loadmaps(self, ctx, initialize=True, removeBorders=True):
        '''
        Loads and renders all levels.
        Initializes the level tree unless otherwise specified.
        Cuts off borders from rendered levels unless otherwise specified.
        '''
        levels = [l[:-2] for l in listdir("levels/vanilla") if l.endswith(".l")]

        # For managing the directions of the items
        tileData = self.bot.get_cog("Admin").tileColors
        dirs = lambda o: o["direction"] * 8 if tileData[o["name"]]["tiling"] in ["0","2","3"] else 0
        renderer = self.bot.get_cog("Baba Is You")

        # Parse and render the level map
        for i,level in enumerate(levels):
            await self.renderMap(level, source="vanilla", dirs=dirs, renderer=renderer, initialize=True, removeBorders=True)
            print(i)

        self.cleanMetadata()

    def readObjects(self, reader):
        '''
        Inner function that parses the contents of a "values.lua" file.
        Returns the largest valid object ID for in-level objects.
        '''
        maxID = 0
        rawline = None
        while rawline != "":
            rawline = reader.readline()
            data = rawline.strip()
            # Done parsing, end of the relevant section
            if data == "}":
                break
            
            index = tryIndex(data, "=")
            # Looking for "key=value" pairs

            # If those are not found, move on
            if len(data) < 2 or index < 0:
                continue
            
            # Since they were found, this means we are now parsing a default object
            item = Item()
            # Determine the object ID of what we're parsing
            data = data[:index].strip()
            o = tryIndex(data, "object")
            if o == 0:
                temp = 0
                try:
                    temp = int(data[6:])
                    # This will eventually leave us with the largest valid ID
                    if temp and temp > maxID:
                        maxID = temp
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
                index = tryIndex(obj, "=")
                if index == -1: continue
                
                # Isolate the two sides of the equals sign
                value = obj[index + 1: len(obj) - 1].strip()
                obj = obj[: index].strip().lower()
                # Update the previously created Item instance with the data we parsed
                self.setItemValue(item, obj, value)
                
                # ID 0 is special: edge
                if item.ID == 0:
                    item.name = "edge"
                    item.obj = "edge"

            # We're done parsing an object and have escaped the loop above.
            # Now we add the item to out cache.
            self.defaultsById[item.ID] = item
            self.defaultsByObject[data] = item
            self.defaultsByName[item.name] = item

        # We've parsed and stored all objects from "values.lua" in cache.
        # Now we only need to add the special cases:
        # Empty tiles
        empty = Item.empty()
        self.defaultsByObject[empty.obj] = empty
        self.defaultsById[empty.ID] = empty
        self.defaultsByName[empty.name] = empty
        # Level tiles
        level = Item.level()
        self.defaultsByObject[level.obj] = level
        self.defaultsById[level.ID] = level
        self.defaultsByName[level.name] = level
        # The largest valid ID we found
        return maxID

    def setItemValue(self, item, obj, value):
        '''
        Sets an Item's attribute to a value.
        '''
        # Most of these attributes are commented out.
        # They may be implemented later, if necessary.
        if obj == "name":
            item.name = value[1:len(value) - 1]
        # elif obj == "sprite":
            # item.sprite = value[1:len(value) - 2]
        # elif obj == "sprite_in_root":
            # item.spriteInRoot = int(value)
        # elif obj == "unittype":
            # item.isObject = value == "\"object\""
        # elif obj == "type":
            # item.type = int(value)
        elif obj == "layer":
            item.layer = int(value)
        # elif obj == "colour":
            # item.color = self.CTS(value)
        # elif obj == "active":
            # item.activeColor = self.CTS(value)
        # elif obj == "tiling":
            # item.tiling = int(value)
        elif obj == "tile":
            item.ID = self.CTS(value)
        # elif obj == "argextra":
            # item.argExtra = value[1:len(value) - 2].replace("\"", "")
        # elif obj == "argtype":
            # item.argType = value[1:len(value) - 2].replace("\"", "")
        # elif obj == "grid":
            # item.grid = self.CTS(value)

    def CTS(self, value):
        '''
        Converts a string from the output of "values.lua" to a number.
        Examples:
        "{1}" -> 1
        "{1, 5}" -> 1<<8 | 5 -> 261
        "1" -> 1
        "1, 5" -> 1<<8 | 5 -> 261
        '''
        startIndex = 0
        endIndex = len(value)
        if value.index("{") == 0:
            startIndex += 1
            endIndex -= 1
        try:
            index = value.index(",")
        except ValueError:
            return int(value)
        x = int(value[startIndex: index - startIndex + 1])
        y = int(value[index + 1: endIndex].strip())
        return (y << 8) | x

    async def readMap(self, filename, source, initialize = False):
        '''
        Parses a .l file's content, given its file path.
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
                    layerCount = int.from_bytes(buffer, byteorder="little") & (2**16 - 1)
                    # Mysterious off-by-one magic
                    for _ in range(layerCount + 1):
                        self.readLayer(stream, grid, version)
                    break

        # We've added the basic objects & their directions. 
        # Now we add everything else:
        # Paths
        grid = self.addPaths(grid)
        # Levels
        grid = self.addLevels(grid, initialize=initialize) # If we want to also initialize the level tree
        # Images
        grid = self.addImages(grid)
        # Special objects
        grid = self.addSpecials(grid)
        # Level metadata
        grid = self.addMetadata(grid)
        # Object changes
        grid = self.addChanges(grid)

        # Makes sure objects within a single cell are rendered in the right order
        grid = self.sortLayers(grid)
        
        return grid

    def sortLayers(self, grid):
        '''
        Sorts the items within each cell of the grid.
        Items are sorted according to their layer attribute, in ascending order.
        '''
        for cell in grid.cells:
            cell.objects.sort(key=lambda x: x.layer)

        return grid

    def addChanges(self, grid):
        '''
        Modifies the objects in the level according to the changes proposed in the level's .ld file.
        '''
        # the .ld file
        info = grid.fp + "d"
        with open(info) as ld:
            changes = {}

            # Go through each line of the file
            raw = None
            while raw != "":
                raw = ld.readline()
                line = raw.strip()
                
                # We're starting parsing the object changes section
                if line == "[tiles]":
                    rawl = None
                    while rawl != "":
                        rawl = ld.readline()
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
                        index = tryIndex(data, "=")
                        if index == -1: continue

                        # These are the bits of information we care about
                        values = ["_name"]
                        for v in values:
                            paramIndex = tryIndex(data, v)
                            if paramIndex != -1:
                                break
                            # Don't need the line anymore, move on
                        if paramIndex == -1:
                            continue
                        
                        # This will be an element of `values`
                        # param = data[paramIndex:index]

                        # The object ID prefixing the line
                        key = data[:paramIndex]
                        changes[key] = data[index + 1:]
        
        # Updates the grid:
        # Replaces old object names with new object names.
        # This is a shallow change; only the name is updated.
        if changes:
            for cell in grid.cells:
                for item in cell.objects:
                    new = changes.get(item.obj)
                    if new is not None:
                        item.name = new
        
        return grid

    def addMetadata(self, grid):
        '''
        Adds level metadata from a level's .ld file to the given Grid.
        Adds the following information:
        * Level name 
        * Subtitle
        * Palette
        * Cursor position
        '''
        # the .ld file
        info = grid.fp + "d"
        # Our data
        name = subtitle = palette = cursorX = cursorY = None
        with open(info) as ld:
            # Go through each line of the file
            line = None
            while line != "":
                line = ld.readline().strip()
                # Level name
                if line.startswith("name="):
                    name = line[5:]
                # Palette (strip .png)
                if line.startswith("palette="):
                    palette = line[8:-4]
                # Level subtitle
                if line.startswith("subtitle="):
                    subtitle = line[9:]
                # Cursor position
                if line.startswith("selectorX="):
                    pos = line[10:]
                    if pos != -1:
                        cursorX = int(pos)
                if line.startswith("selectorY="):
                    pos = line[10:]
                    if pos != -1:
                        cursorY = int(pos)
        # Add cursor
        if cursorX is not None:
            cursorPosition = flatten(cursorX, cursorY, grid.width)
            grid.cells[cursorPosition].objects.append(self.defaultsByName["cursor"])

        # Add other data
        grid.name = name
        grid.subtitle = subtitle
        if palette is None:
            grid.palette = "default"
        else:
            grid.palette = palette

        return grid

    def addLevels(self, grid, initialize=False):
        '''
        Adds raw level objects from within a level to the given Grid.
        Data is parsed from the .ld file associated with the level.
        if `initialize` is True, adds levels to the global level tree.
        '''
        # the .ld file
        info = grid.fp + "d"
        with open(info) as ld:
            levels = {}
            levelCount = 0
            mapID = ""

            # Go through each line of the file
            line = None
            while line != "":
                line = ld.readline().strip()
                # How many levels are there in the map??
                if line.startswith("levels="):
                    levelCount = int(line[7:])
                # When initializing the level tree:
                if initialize and line.startswith("mapid="):
                    mapID = line[6:]
                
                # We're starting parsing levels
                if line == "[levels]":
                    data = None
                    while data != "":
                        data = ld.readline().strip()
                        
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
                            values = ["X", "Y", "file", "number", "name"]
                        else:
                            values = ["X", "Y"]
                        for v in values:
                            paramIndex = tryIndex(data, v)
                            if paramIndex != -1:
                                break
                            # Don't need the line anymore, move on
                        if paramIndex == -1:
                            continue
                        
                        # This will be an element of `values`
                        param = data[paramIndex:index]

                        # The number prefixing the line
                        key = data[:paramIndex]
                        if key.isnumeric():
                            # Ignore levels with IDs above the levelcount
                            # Because those are not actual levels???
                            if int(key) <= levelCount:
                                # If the level is new
                                if levels.get(key) is None:
                                    levels[key] = {}
                                # Store the level position
                                levels[key][param] = data[index + 1:]

            # Update our grid object with the levels
            for data in levels.values():
                position = flatten(data["X"], data["Y"], grid.width)
                level = Item.level()
                level.position = position
                # Levels are (sort of) like any other object
                grid.cells[position].objects.append(level)

                # Handle the level tree
                if initialize:
                    # The parent node
                    node = {
                        "mapID"  : mapID,
                        "levels" : {}
                    }
                    # Key
                    parent = grid.filename
                    # Each level within
                    for l in levels.values():
                        child = {
                            "number" : l["number"],
                            "name"   : l["name"]
                        }
                        # nice nested level ids
                        node["levels"][l["file"]] = child
                                                
                    self._levels[parent] = node
            
            return grid
    
    def addPaths(self, grid):
        '''
        Adds raw path objects from within a level to the given Grid.
        Objects are added to the Grid as regular objects without path information.
        Data is parsed from the .ld file associated with the level.
        '''
        # the .ld file
        info = grid.fp + "d"
        with open(info) as ld:
            paths = {}
            pathCount = 0

            # Go through each line of the file
            line = None
            while line != "":
                line = ld.readline().strip()                
                # How many path objects are there in the map?
                if line.startswith("paths="):
                    pathCount = int(line[6:])
                
                # We've started parsing paths
                if line == "[paths]":
                    data = None
                    while data != "":
                        data = ld.readline().strip()
                        
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
                            paramIndex = tryIndex(data, v)
                            if paramIndex != -1:
                                break
                        if paramIndex == -1:
                            continue

                        # This will be "X", "Y", "object" or "dir"
                        param = data[paramIndex:index]

                        # The number prefixing the line
                        key = data[:paramIndex]
                        if key.isnumeric():
                            # Ignore paths with IDs above the pathcount
                            # Because those are not actual paths???
                            if int(key) <= pathCount:
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
                path.ID        = self.defaultsByObject[data["object"]].ID
                path.name      = self.defaultsByObject[data["object"]].name
                # Paths are (sort of) like any other object
                grid.cells[position].objects.append(path)
            
            
            return grid

    def addImages(self, grid):
        '''
        Adds background image data from a level to the given Grid.
        Data is parsed from the .ld file associated with the level.
        '''
        # The .ld file
        info = grid.fp + "d"
        with open(info) as ld:
            images = {}

            # Go through each line of the file
            line = None
            while line != "":
                line = ld.readline().strip()            
                # This is where we begin parsing
                if line == "[images]":
                    data = None
                    while data != "":
                        data = ld.readline().strip()
                        
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
        sortedImages = dict(sorted(images.items(), key=lambda x: int(x[0])))
        sortedList = [s for s in sortedImages.values()]
        # Update our grid
        grid.images = sortedList
        return grid

    def addSpecials(self, grid):
        '''
        Adds special objects from within a level to the given Grid.
        Data is parsed from the .ld file associated with the level.
        '''
        # the .ld file
        info = grid.fp + "d"
        with open(info) as ld:
            specials = {}
            specialCount = 0

            # Go through each line of the file
            line = None
            while line != "":
                line = ld.readline().strip()                
                # How many speicl objects are there in the map?
                if line.startswith("specials="):
                    specialCount = int(line[9:])
                
                # We've started parsing paths
                if line == "[specials]":
                    data = None
                    while data != "":
                        data = ld.readline().strip()
                        
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
                            paramIndex = tryIndex(data, v)
                            if paramIndex != -1:
                                break
                        if paramIndex == -1:
                            continue
                        
                        # This will be "X", or "Y" or "data"
                        param = data[paramIndex:index]

                        # The number prefixing the line
                        key = data[:paramIndex]
                        if key.isnumeric():
                            # Ignore specials with IDs above the pathcount
                            # Because those are not actual specials???
                            if int(key) <= specialCount:
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

        return grid
            
    def readLayer(self, stream, grid, version):
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

        dataBlocks = int.from_bytes(stream.read(1), byteorder="little") & (2**8 - 1)
        assert not (dataBlocks < 1 and dataBlocks > 2)

        # MAIN
        stream.read(4)
        buffer = stream.read(4)
        compressedSize = int.from_bytes(buffer, byteorder="little") & (2**32 - 1)
        nextPosition = stream.tell() + compressedSize

        zobj = zlib.decompressobj()
        mapBuffer = zobj.decompress(stream.read(size * 2))
        read = len(mapBuffer)
        
        read >>= 1
        

        stream.seek(nextPosition)

        items = []
        for j,k in zip(range(read), range(0, 2 * read, 2)):
            cell = grid.cells[j]
            ID = int.from_bytes(mapBuffer[k : k + 16], byteorder="little") & (2**16 - 1)

            item = self.defaultsById.get(ID)
            if item is not None:
                item = item.copy()
            else:
                item = Item.empty()
                ID = -1
            item.position = j
            items.append(item)
            
            if ID != -1:
                cell.objects.append(item)

        if dataBlocks == 2:
            # DATA
            mapBuffer = stream.read(13)
            compressedSize = int.from_bytes(mapBuffer[9:], byteorder="little") & (2**32 - 1)
            nextPosition = stream.tell() + compressedSize

            zobj = zlib.decompressobj()
            mapBuffer = zobj.decompress(stream.read(size))
            read = len(mapBuffer)

            stream.seek(nextPosition)

            for j in range(read):
                item = items[j]
                item.direction = mapBuffer[j]

def setup(bot):
    bot.add_cog(Reader(bot))