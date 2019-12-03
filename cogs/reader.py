import discord
import json
import zlib

from discord.ext import commands

def flatten(x, y, width):
    '''
    Return the flattened position of a coordinate in a grid of specified width
    '''
    return int(y) * width + int(x)

class Grid:
    '''
    This stores the information of a single Baba level, in a format readable by the renderer.
    '''
    def __init__(self, fp):
        '''
        Initializes a blank grid, given a path to the level file. 
        This should not be used; you should use Reader.readMap() instead to generate a filled grid.
        '''
        self.images = []
        self.width = 0
        self.height = 0
        self.cells = []
        self.fp = fp
    
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
            "objects":m,
            "images":self.images
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
    def __init__(self, *, ID=None, obj=None, name=None, position=None, direction=None, extra=None):
        '''
        Returns an Item with the given parameters.
        '''
        self.ID = ID
        self.obj = obj
        self.name = name
        self.position = position
        self.direction = direction
        self.extra = extra

    @classmethod
    def edge(cls):
        '''
        Returns an Item representing an edge tile.
        '''
        return Item(ID=0, obj="edge", name="edge")
    
    @classmethod
    def empty(cls):
        '''
        Returns an Item representing an empty tile.
        '''
        return Item(ID=-1, obj="empty", name="empty")
    
    @classmethod
    def level(cls):
        '''
        Returns an Item representing a level object.
        '''
        return Item(ID=-2, obj="level", name="level")

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

        with open("values.lua") as reader:
            line = None
            while line != "":
                line = reader.readline()
                try:
                    # Raises ValueError if we're not at the relevant section yet
                    index = line.index("tileslist =")
                except ValueError:
                    continue
                else:
                    if index == 0:
                        # Parsing begins
                        self.readObjects(reader)
                        break

    @commands.command()
    @commands.is_owner()
    async def parseMap(self, ctx, level):
        safe = self.readMap(f"levels/{level}.l")
        return await self.bot.send(ctx, "Done.")

    def readObjects(self, reader):
        '''
        Inner function that parses the contents of a "values.lua" file.
        Returns the largest valid object ID for in-level objects.
        '''
        maxID = 0
        data = None
        while data != "":
            data = reader.readline().strip()
            # Done parsing, end of the relevant section
            if data == "}":
                break
            
            try:
                # Looking for "key=value" pairs
                index = data.index("=")
            except:
                index = -1

            # If those are not found, move on
            if len(data) < 2 or index < 0:
                continue
            
            # Since they were found, this means we are now parsing a default object
            item = Item()
            # Determine the object ID of what we're parsing
            data = data[:index].strip()
            try:
                o = data.index("object")
            except:
                o = -1
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
            obj = None
            while obj != "":
                obj = reader.readline().strip()
                # We're done parsing, move on
                if obj == "},":
                    break
                
                try:
                    # "value=obj" pairs, please
                    index = obj.index("=")
                except:
                    # Not found? move on
                    index = -1
                    continue
                
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

        # We've parsed and stored all objects from "values.lua" in cache.
        # Now we only need to add the special cases:
        # Empty tiles
        empty = Item.empty()
        self.defaultsByObject[empty.obj] = empty
        self.defaultsById[empty.ID] = empty
        # Level tiles
        level = Item.level()
        self.defaultsByObject[level.obj] = level
        self.defaultsById[level.ID] = level
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
        # elif obj == "layer":
            # item.layer = int(value)
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

    async def readMap(self, fp):
        '''
        Parses a .l file's content, given its file path.
        Returns a Grid object containing the level data.
        '''
        print(f"Level: {fp}")
        # mapBuffer = bytearray()
        grid = Grid(fp)
        with open(fp, "rb") as stream:
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
                    print(f"Layers: {layerCount}")
                    # Mysterious off-by-one magic
                    for _ in range(layerCount + 1):
                        self.readLayer(stream, grid, version)
                    break

        # We've added the basic objects & their directions. 
        # Now we add everything else:
        # Paths
        grid = self.addPaths(grid)
        # Levels
        grid = self.addLevels(grid)
        # Images
        grid = self.addImages(grid)
        # Special objects
        grid = self.addSpecials(grid)

        # For debugging, delete this 
        m = grid.serialize()
        tileData = self.bot.get_cog("Admin").tileColors
        safe = []
        for row in m["objects"]:
            x = [[f"{obj['name']}:{8 * obj['direction']}" if tileData[obj['name']]['tiling'] in ['0', '2', '3'] else obj['name'] for obj in cell] for cell in row]
            safe.append(x)
        
        return safe

    def addLevels(self, grid):
        '''
        Adds raw level objects from within a level to the given Grid.
        Data is parsed from the .ld file associated with the level.
        '''
        # the .ld file
        info = grid.fp + "d"
        with open(info) as ld:
            levels = {}
            levelCount = 0

            # Go through each line of the file
            line = None
            while line != "":
                line = ld.readline().strip()
                # How many levels are there in the map??
                if line.startswith("levels="):
                    levelCount = int(line[7:])
                
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
                        try:
                            paramIndex = data.index("X")
                        except ValueError:
                            try:
                                paramIndex = data.index("Y")
                            except ValueError:
                                # we don't need the line anymore, move on
                                continue 
                        # This will be "X" or "Y"
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
                        try:
                            paramIndex = data.index("X")
                        except ValueError:
                            try:
                                paramIndex = data.index("Y")
                            except ValueError:
                                try:
                                    paramIndex = data.index("object")
                                except ValueError:
                                    try:
                                        paramIndex = data.index("dir")
                                    except ValueError:
                                        # we don't need the line anymore, move on
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
                        try:
                            paramIndex = data.index("X")
                        except ValueError:
                            try:
                                paramIndex = data.index("Y")
                            except ValueError:
                                try:
                                    paramIndex = data.index("data")
                                except ValueError:
                                    # we don't need the line anymore, move on
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

        print(f"Data blocks: {dataBlocks}")
        # MAIN
        stream.read(4)
        buffer = stream.read(4)
        compressedSize = int.from_bytes(buffer, byteorder="little") & (2**32 - 1)
        nextPosition = stream.tell() + compressedSize

        zobj = zlib.decompressobj()
        mapBuffer = zobj.decompress(stream.read(size * 2))
        read = len(mapBuffer)
        
        read >>= 1
        
        print(f"Length (Block 1): {read}")

        stream.seek(nextPosition)

        items = []
        for j,k in zip(range(read), range(0, 2 * read, 2)):
            cell = grid.cells[j]
            ID = int.from_bytes(mapBuffer[k : k + 16], byteorder="little") & (2**16 - 1)


            if ID in self.defaultsById:
                item = Item()
                item.ID = ID
                item.name = self.defaultsById[ID].name
                item.obj = self.defaultsById[ID].obj
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
            print(f"Length (Block 2): {read}")

            stream.seek(nextPosition)

            for j in range(read):
                item = items[j]
                item.direction = mapBuffer[j]

def setup(bot):
    bot.add_cog(Reader(bot))