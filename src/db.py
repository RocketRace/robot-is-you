from __future__ import annotations

from dataclasses import dataclass
from sqlite3.dbapi2 import Row
import asqlite
from PIL import Image
from .constants import DIRECTIONS
class Database:
    '''Everything relating to persistent readable & writable data'''
    conn: asqlite.Connection
    async def connect(self, db: str) -> None:
        '''Startup'''
        self.conn = await asqlite.connect(db) # type: ignore
        print("Initialized database connection.")
        await self.create_tables()
        print("Verified database tables.")

    async def close(self) -> None:
        '''Teardown'''
        await self.conn.close()
    
    async def create_tables(self) -> None:
        '''Creates tables in the database according to 
        a schema in code. (Useful for documentation.)
        '''
        async with self.conn.cursor() as cur:
            await cur.execute(
                # `name` is not specified to be a unique field.
                # We allow multiple "versions" of a tile to exist, 
                # to account for differences between "world" and "editor" tiles.
                # One example of this is with `belt` -- its color inside levels 
                # (which use "world" tiles) is different from its editor color.
                # These versions are differentiated by `version`.
                #
                # For tiles where the active/inactive distinction doesn't apply
                # (i.e. all non-text tiles), only `active_color` fields are
                # guaranteed to hold a meaningful, non-null value.
                #
                # `text_direction` defines whether a property text tile is 
                # "pointed towards" any direction. It is null otherwise. 
                # The directions are right: 0, up: 8, left: 16, down: 24.
                # 
                # `tags` is a tab-delimited sequence of strings. The empty
                # string denotes no tags.
                '''
                CREATE TABLE IF NOT EXISTS tiles (
                    name TEXT NOT NULL,
                    sprite TEXT NOT NULL,
                    source TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    inactive_color_x INTEGER DEFAULT 3,
                    inactive_color_y INTEGER DEFAULT 0,
                    active_color_x INTEGER NOT NULL DEFAULT 0,
                    active_color_y INTEGER NOT NULL DEFAULT 3,
                    tiling INTEGER NOT NULL DEFAULT -1,
                    text_type INTEGER,
                    text_direction INTEGER,
                    tags TEXT NOT NULL DEFAULT "",
                    UNIQUE(name, version)
                );
                '''
            )
            # We create different tables for levelpacks and custom levels.
            # While both share some fields, there are mutually exclusive
            # fields which are more sensible in separate tables.
            #
            # The world/id combination is unique across levels. However,
            # a world can have multiple levels and multiple worlds can share
            # a level id. Thus neither is unique alone.
            await cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS levels (
                    level_id TEXT NOT NULL,
                    world TEXT NOT NULL,
                    name TEXT NOT NULL,
                    subtitle TEXT,
                    number INTEGER,
                    style INTEGER,
                    parent TEXT,
                    map_id TEXT,
                    UNIQUE(level_id, world)
                );
                '''
            )
            await cur.execute(
                # There have been multiple valid formats of level 
                # codes, so we don't assume a constant-width format.
                '''
                CREATE TABLE IF NOT EXISTS custom_levels (
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    subtitle TEXT,
                    difficulty INTEGER,
                    author TEXT
                );
                '''
            )
            await cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS letters (
                    mode TEXT,
                    char TEXT,
                    width INTEGER,
                    sprite_0 BLOB,
                    sprite_1 BLOB,
                    sprite_2 BLOB
                );
                '''
            )
            await cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    blacklisted INTEGER,
                    silent_commands INTEGER,
                    render_background INTEGER
                );
                '''
            )

    async def tile(self, name: str, *, editor: bool = True) -> TileData | None:
        '''Convenience method to fetch a single thing of tile data. Returns None on failure.'''
        version = 1 if editor else 0
        async with self.conn.cursor() as cur:
            await cur.execute(
                '''
                SELECT * FROM tiles WHERE name == ? AND version == ?;
                ''',
                name, version
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return TileData.from_row(row)
    
    def plate(self, direction: int | None, wobble: int) -> tuple[Image.Image, tuple[int, int]]:
        '''Plate sprites. Raises FileNotFoundError on failure.'''
        if direction is None:
            return (
                Image.open(f"data/plates/plate_property_0_{wobble+1}.png").convert("RGBA"),
                (0, 0)
            )
        return (
            Image.open(f"data/plates/plate_property{DIRECTIONS[direction]}_0_{wobble+1}.png").convert("RGBA"),
            (3, 3)
        )

@dataclass
class TileData:
    name: str
    sprite: str
    source: str
    inactive_color: tuple[int, int]
    active_color: tuple[int, int]
    tiling: int
    text_type: int | None
    text_direction: int | None
    tags: list[str]

    @classmethod
    def from_row(cls, row: Row) -> TileData:
        '''Create a tiledata object from a database row'''
        return TileData(
            row["name"],
            row["sprite"],
            row["source"],
            (row["inactive_color_x"], row["inactive_color_y"]),
            (row["active_color_x"], row["active_color_y"]),
            row["tiling"],
            row["text_type"],
            row["text_direction"],
            row["tags"].split("\t")
        )

class DataAccess:
    '''Means through which most bot data is accessed.
    
    This will be hooked up to a database driver eventually.
    '''
    _tile_data: dict
    _level_tile_data: dict
    _letter_data: dict
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        # this is all temporary until I migrate to a DB

    def tile_datas(self) -> Iterable[tuple[str, dict]]:
        '''All them'''
        yield from self._tile_data.items()

    def tile_data(self, tile: str) -> dict | None:
        '''Tile data. Returns None on failure.'''
        return self._tile_data.get(tile)
    
    def level_tile_data(self, tile: str) -> dict | None:
        '''Level tile overrides. Returns None on failure.'''
        return self._level_tile_data.get(tile)
    
    def letter_width(self, char: str, mode: str, *, greater_than: int) -> int:
        '''The minimum letter width for the given char of the give mode,
        such that the width is more than the given width.

        Raises KeyError(char) on failure.
        '''
        extras = {
            "*": "asterisk"
        }
        char = extras.get(char, char)
        try:
            return min(width for width in self._letter_data[mode][char] if width > greater_than)
        # given width too large
        except ValueError:
            raise KeyError(char)

    def letter_sprite(self, char: str, mode: str, width: int, wobble: int, *, seed: int | None) -> Image.Image:
        '''Letter sprites. Raises FileNotFoundError on failure.'''
        choices = self._letter_data[mode][char][width]
        if seed is None:
            choice = random.choice(choices)
        else:
            # This isn't uniformly random since `seed` ranges from 0 to 255,
            # but it's "good enough" for me and "random enough" for an observer.
            choice = choices[seed % len(choices)]
        return Image.open(
            f"target/letters/{mode}/{char}/{width}/{choice}_{wobble}.png"
        )
