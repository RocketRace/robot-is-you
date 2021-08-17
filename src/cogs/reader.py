from __future__ import annotations

import asyncio
import base64
import configparser
import io
from src.db import CustomLevelData, LevelData
import zlib
from os import listdir, stat
from typing import BinaryIO, TextIO

import aiohttp
from discord.ext import commands

from ..tile import RawTile
from ..types import Bot, Context


def flatten(x: int, y: int, width: int) -> int:
    '''Return the flattened position of a coordinate in a grid of specified width'''
    return int(y) * width + int(x)

class Grid:
    '''This stores the information of a single Baba level, in a format readable by the renderer.'''
    def __init__(self, filename: str, world: str):
        '''Initializes a blank grid, given a path to the level file. 
        This should not be used; you should use Reader.read_map() instead to generate a filled grid.
        '''
        # The location of the level
        self.fp: str = f"data/levels/{world}/{filename}.l"
        self.filename: str = filename
        self.world: str = world
        # Basic level information
        self.name: str = ""
        self.subtitle: str | None = None
        self.palette: str = "default"
        self.images: list[str] = []
        # Object information
        self.width: int = 0
        self.height: int = 0
        self.cells: list[list[Item]] = []
        # Parent level and map identification
        self.parent: str | None = None
        self.map_id: str | None = None
        self.style: int | None = None
        self.number: int | None = None
        # Custom levels
        self.author: str | None = None
    
    def raw_grid(self) -> list[list[list[RawTile]]]:
        '''Returns an unflattened version of the grid.'''
        height = self.height
        width = self.width
        dirs = "ruld"
        return [
            [
                [
                    RawTile(name=o.name or "error", variants=[
                        dirs[(o.direction or 0) // 8]
                    ] + 
                        ["/".join(tuple(map(str, o.color)))] if o.color is not None else []
                    )
                    # "".join([
                    #     o.name or "error",
                    #     f":{o.direction * 8}" if o.direction is not None else "",
                    #     ":" + "/".join(tuple(map(str, o.color))) if o.color is not None else ""
                    # ])
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
    def __init__(self, *, ID: int | None = None, obj: str | None = None, name: str | None = None, color: tuple[int, int] | None = None, position: int = None, direction: int = None, extra = None, layer: int = 0):
        '''Returns an Item with the given parameters.'''
        self.ID: int | None = ID
        self.obj: str | None = obj
        self.name: str | None = name
        self.color: tuple[int, int] | None = color
        self.position: int | None = position
        self.direction: int | None = direction
        self.extra = extra
        self.layer: int = layer

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
    def level(cls, color: tuple[int, int] = (0, 3)) -> Item:
        '''Returns an Item representing a level object.'''
        return Item(ID=-2, obj="level", name="level", color=color, layer=20)

class Reader(commands.Cog, command_attrs=dict(hidden=True)):
    '''A class for parsing the contents of level files.'''
    def __init__(self, bot: Bot):
        '''Initializes the Reader cog.
        Populates the default objects cache from a data/values.lua file.
        '''
        self.bot = bot
        self.defaults_by_id = {}
        self.defaults_by_object = {}
        self.defaults_by_name = {}
        self.parent_levels: dict[str, tuple[str, dict[str, tuple[int, int]]]] = {}

        with open("data/values.lua") as reader:
            line = None
            while line != "":
                line = reader.readline()
                index = line.find("tileslist =")
                if index == -1:
                    continue
                elif index == 0:
                    # Parsing begins
                    self.read_objects(reader)
                    break
        
    async def render_custom_level(self, code: str) -> CustomLevelData:
        '''Renders a custom level. code should be valid (but is checked regardless)'''
        async with aiohttp.request("GET", f"https://baba-is-bookmark.herokuapp.com/api/level/raw/l?code={code.upper()}") as resp:
            resp.raise_for_status()
            data = await resp.json()
            b64 = data["data"]
            decoded = base64.b64decode(b64)
            raw_l = io.BytesIO(decoded)
        async with aiohttp.request("GET", f"https://baba-is-bookmark.herokuapp.com/api/level/raw/ld?code={code.upper()}") as resp:
            resp.raise_for_status()
            data = await resp.json()
            raw_s = data["data"]
            raw_ld = io.StringIO(raw_s)

        grid = self.read_map(code, source="levels", data=raw_l)
        grid = await self.read_metadata(grid, data=raw_ld, custom=True)

        objects = grid.raw_grid()
        # Strips the borders from the render
        # (last must be popped before first to preserve order)
        objects.pop(grid.height - 1)
        objects.pop(0)
        for row in objects:
            row.pop(grid.width - 1)
            row.pop(0)
        out = f"target/renders/levels/{code}.gif"
        tiles = await self.bot.handlers.handle_grid(objects, tile_borders=True, ignore_bad_directions=True)
        await self.bot.renderer.render(tiles, palette=grid.palette, background=(0, 4), out=out)
        
        data = CustomLevelData(code.lower(), grid.name, grid.subtitle, grid.author)

        await self.bot.db.conn.execute(
            '''
            INSERT INTO custom_levels
            VALUES (?, ?, ?, ?)
            ON CONFLICT(code) 
            DO NOTHING;
            ''',
            code.lower(), grid.name, grid.subtitle, grid.author
        )

        return data

    async def render_level(
        self, 
        filename: str, 
        source: str, 
        initialize: bool = False, 
        remove_borders: bool = False, 
        keep_background: bool = False, 
        tile_borders: bool = False
    ) -> LevelData:
        '''Loads and renders a level, given its file path and source. 
        Shaves off the borders if specified.
        '''
        # Data
        grid = self.read_map(filename, source=source)
        grid = await self.read_metadata(grid, initialize_level_tree=initialize)
        objects = grid.raw_grid()

        # Shave off the borders:
        if remove_borders:
            objects.pop(grid.height - 1)
            objects.pop(0)
            for row in objects:
                row.pop(grid.width - 1)
                row.pop(0)

        # Handle sprite variants
        tiles = await self.bot.handlers.handle_grid(objects, ignore_bad_directions=True, tile_borders=tile_borders, ignore_editor_overrides=True)

        # (0,4) is the color index for level backgrounds
        background = (0,4) if keep_background else None

        # Render the level
        await self.bot.renderer.render(
            tiles,
            palette=grid.palette,
            images=grid.images,
            image_source=grid.world,
            background=background,
            out=f"target/renders/{grid.world}/{grid.filename}.gif",
        )
        # Return level metadata
        return LevelData(filename, source, grid.name, grid.subtitle, grid.number, grid.style, grid.parent, grid.map_id)

    @commands.command()
    @commands.is_owner()
    async def loadmap(self, ctx: Context, source: str, filename: str):
        '''Loads a given level's image.'''
        # Parse and render
        await self.render_level(
            filename, 
            source=source, 
            initialize=False, 
            remove_borders=True,
            keep_background=True,
            tile_borders=True
        )
        # This should mostly just be false
        await ctx.send(f"Rendered level at `{source}/{filename}`.")

    async def clean_metadata(self, metadata: dict[str, LevelData]):
        '''Cleans up level metadata from `self.parent_levels` as well as the given dict, and updates the DB.'''

        for map_id, child_levels in self.parent_levels.values():
            remove = []
            for child_id in child_levels:
                # remove levels which point to maps themselves (i.e. don't mark map as "lake-blah: map")
                # as a result of this, every map will have no parent in its name - so it'll just be 
                # something like "chasm" or "center"
                if self.parent_levels.get(child_id) is not None:
                    remove.append(child_id)
            # avoid mutating a dict while iterating over it
            for child_id in remove:
                child_levels.pop(child_id)
        for map_id, child_levels in self.parent_levels.values():
            for child_id, (number, style) in child_levels.items():
                metadata[child_id].parent = map_id
                metadata[child_id].number = number
                metadata[child_id].style = style

        self.parent_levels.clear()
        await self.bot.db.conn.executemany(
            '''
            INSERT INTO levels VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id, world) DO UPDATE SET
                name=excluded.name,
                subtitle=excluded.subtitle,
                number=excluded.number,
                style=excluded.style,
                parent=excluded.parent,
                map_id=excluded.map_id;
            ''',
            [(l.id, l.world, l.name, l.subtitle, l.number, l.style, l.parent, l.map_id) for l in metadata.values()]
        )

    @commands.command()
    @commands.is_owner()
    async def loadmaps(self, ctx: Context):
        '''Loads and renders all levels.
        Initializes the level tree unless otherwise specified.
        Cuts off borders from rendered levels unless otherwise specified.
        '''
        levels = [l[:-2] for l in listdir("data/levels/baba") if l.endswith(".l")]

        # Parse and render the level map
        await ctx.send("Loading maps...")
        metadatas = {}
        total = len(levels)
        for i,level in enumerate(levels):
            metadata = await self.render_level(
                level,
                source="baba", 
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
        await self.clean_metadata(metadatas)
        await ctx.send(f"{ctx.author.mention} Database updated. Done.")


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
            
            index = data.find("=")
            # Looking for "key=value" pairs

            # If those are not found, move on
            if len(data) < 2 or index < 0:
                continue
            
            # Since they were found, this means we are now parsing a default object
            item = Item()
            # Determine the object ID of what we're parsing
            data = data[:index].strip()
            o = data.find("object")
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
                index = obj.find("=")
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

    def parse_literal(self, value: str) -> int:
        '''Converts a string from the output of data/values.lua to a number.
        Examples:
        "{1}" -> 1
        "{1, 5}" -> 1<<8 | 5 -> 261
        "1" -> 1
        "1, 5" -> 1<<8 | 5 -> 261
        '''
        start_index = 0
        end_index = len(value)
        if value.find("{") == 0:
            start_index += 1
            end_index -= 1
        try:
            index = value.index(",")
        except ValueError:
            return int(value)
        x = int(value[start_index: index - start_index + 1])
        y = int(value[index + 1: end_index].strip())
        return (y << 8) | x

    def read_map(self, filename: str, source: str, data: BinaryIO | None = None) -> Grid:
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


    async def read_metadata(self, grid: Grid, initialize_level_tree: bool = False, data: TextIO | None = None, custom: bool = False) -> Grid:
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
            # difficulty_string = config.get("general", "difficulty", fallback=None)
            grid.author = config.get("general", "author", fallback=None)

        # Only applicable to old style cursors
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

        child_levels = {}

        # Add level objects & initialize level tree
        level_count = config.getint("general", "levels", fallback=0)
        for i in range(level_count):
            # Level colors can sometimes be omitted, defaults to white
            color = config.get("levels", f"{i}colour", fallback=None)
            if color is None:
                level = Item.level()
            else:
                c_0, c_1 = color.split(",")
                level = Item.level((int(c_0), int(c_1)))
            
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

            if initialize_level_tree and grid.map_id is not None:
                level_file = config.get("levels", f"{i}file")
                # Each level within
                child_levels[level_file] = (number, style)
        
        # Initialize the level tree
        # If map_id is None, then the levels are actually pointing back to this level's parent
        if initialize_level_tree and grid.map_id is not None:
            # specials are only used for special levels at the moment
            special_count = config.getint("general", "specials", fallback=0)
            for i in range(special_count):
                special_data = config.get("specials", f"{i}data")
                special_kind, *special_rest = special_data.split(",")
                if special_kind == "level":
                    # note: because of the comma separation these are still strings
                    level_file, style, number, *_ = special_rest
                    child = (int(number), int(style))
                    # print("adding spec to node", parent, grid.map_id, level_file, child)
                    child_levels[level_file] = child
                
            # merges both normal level & special level data together
            if child_levels:
                self.parent_levels[grid.filename] = (grid.map_id, child_levels)

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
                    change = changes[item.obj] # type: ignore
                    if "name" in change:
                        if await self.bot.db.tile(change["name"], maximum_version=1000 if custom else 0) is not None:
                            item.name = change["name"]
                        else:
                            item.name = "default"
                    # The sprite overrides the name in this case
                    if "image" in change:
                        if await self.bot.db.tile(change["image"], maximum_version=1000 if custom else 0) is not None:
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
                        x, y = change["colour"].split(",")
                        item.color = (int(x), int(y))
                    if "activecolour" in change and item.name is not None and item.name.startswith("text_"):
                        x, y = change["activecolour"].split(",")
                        item.color = (int(x), int(y))

        # Makes sure objects within a single cell are rendered in the right order
        # Items are sorted according to their layer attribute, in ascending order.
        for cell in grid.cells:
            cell.sort(key=lambda x: x.layer)
        
        return grid
        
    def read_layer(self, stream: BinaryIO, grid: Grid):
        buffer = stream.read(4)
        grid.width = int.from_bytes(buffer, byteorder="little")
        
        buffer = stream.read(4)
        grid.height = int.from_bytes(buffer, byteorder="little")
        
        size = grid.width * grid.height
        if size > 10000:
            raise ValueError(size)
        if grid.width > 1000:
            raise ValueError(size)
        if grid.height > 1000:
            raise ValueError(size)
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

def setup(bot: Bot):
    bot.add_cog(Reader(bot))
