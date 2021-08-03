from __future__ import annotations

import pathlib
from sqlite3.dbapi2 import Cursor

import asqlite


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
        '''Ensure tables exist, provide schema in code'''
        # context-managed cursor transactions auto-commit
        async with self.conn.cursor() as cur:
            await cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS tiles (
                    name TEXT UNIQUE NOT NULL,
                    sprite TEXT NOT NULL,
                    source TEXT NOT NULL,
                    inactive_color_x INTEGER,
                    inactive_color_y INTEGER,
                    active_color_x INTEGER,
                    active_color_y INTEGER,
                    editor_inactive_color_x INTEGER,
                    editor_inactive_color_y INTEGER,
                    editor_active_color_x INTEGER,
                    editor_active_color_y INTEGER,
                    tiling INTEGER,
                    text_direction INTEGER,
                    tags TEXT
                );
                '''
            )
            await cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS levels (
                    id TEXT UNIQUE NOT NULL,
                    world TEXT NOT NULL,
                    name TEXT,
                    subtitle TEXT,
                    number INTEGER,
                    style INTEGER,
                    parent TEXT,
                    map_id TEXT
                );
                '''
            )
            await cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS custom_levels (
                    code TEXT UNIQUE NOT NULL,
                    name TEXT,
                    subtitle TEXT,
                    difficulty INTEGER,
                    author TEXT
                );
                '''
            )
            await cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS letters (
                    char CHARACTER(1),
                    width INTEGER,
                    mode INTEGER
                );
                '''
            )
            await cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS users (
                    blacklisted INTEGER,
                    silent_commands INTEGER,
                    render_background INTEGER
                );
                '''
            )

    async def tile(self, name: str, use_editor_colors: bool = True) -> dict | None:
        '''A single thing of tile data. Returns None on failure.'''
        async with self.conn.cursor() as cur:
            await cur.execute(
                '''
                SELECT * FROM tiles WHERE name == ?;
                ''',
                name
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return dict(zip(row.keys(), row))
        
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
