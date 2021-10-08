from __future__ import annotations

import collections
import configparser
import itertools
import json
import os
import pathlib
import re
import zipfile
from io import BytesIO
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord.ext import commands
from PIL import Image, ImageChops, ImageDraw
from src import constants, synchronization

from ..db import TileData
from ..types import Context

if TYPE_CHECKING:
    from ...ROBOT import Bot

class OwnerCog(commands.Cog, name="Admin", command_attrs=dict(hidden=True)):
    async def bot_check(self, ctx: Context):
        row = await self.bot.db.conn.fetchone(
            '''
            SELECT (blacklisted) FROM users
            WHERE user_id == ?;
            ''',
            ctx.author.id
        )
        if row is None:
            return True
        return row["blacklisted"]
        
    def __init__(self, bot: Bot):
        self.bot = bot
        self.identifies = []
        self.resumes = []
        # Are assets loading?
        self.bot.loading = False
            
    @commands.command(aliases=["load", "reload"])
    @commands.is_owner()
    async def reloadcog(self, ctx: Context, cog: str = ""):
        '''Reloads extensions within the bot while the bot is running.'''
        if cog and f"src.cogs.{cog}" not in self.bot.extensions.keys():
            return await ctx.send("Unknown extension provided.")
        
        @synchronization.CogRefreshEvent(f"src.cogs.{cog}" if cog else None)
        async def callback():
            await ctx.send("Reloaded cogs from all instances.")
        
        await self.bot.request(callback)

    @commands.command(aliases=["reboot"])
    @commands.is_owner()
    async def restart(self, ctx: Context):
        '''Restarts the bot process.'''
        await ctx.send("Restarting bot process...")
        self.bot.exit_code = 1
        await self.bot.close()

    @commands.is_owner()
    @commands.command(aliases=["kill", "yeet", "defeat", "empty"])
    async def logout(self, ctx: Context):
        '''Kills the bot process.'''
        if ctx.invoked_with == "yeet":
            await ctx.send("Yeeting bot process...")
        elif ctx.invoked_with == "defeat":
            await ctx.send("[Z] undo [R] retry")
        elif ctx.invoked_with == "empty":
            await ctx.send("_ _")
        else:
            await ctx.send("Killing bot process...")
        await self.bot.close()

    @commands.is_owner()
    @commands.group(invoke_without_subcommand=True, name="not")
    async def not_(self, ctx: Context):
        pass

    @commands.is_owner()
    @not_.command()
    async def robot(self, ctx: Context):
        await ctx.send("Poof!")
        await self.bot.close()

    @commands.command()
    @commands.is_owner()
    async def ban(self, ctx: Context, user: int):
        await self.bot.db.conn.execute(
            '''
            INSERT INTO users (user_id, blacklisted)
            VALUES(?, 1) 
            ON CONFLICT(user_id) 
            DO UPDATE SET blacklisted=1;
            ''',
            user
        )
        await ctx.send(f"`{user}` bent.")

    @commands.command()
    @commands.is_owner()
    async def leave(self, ctx: Context, guild: Optional[discord.Guild] = None):
        if guild is None:
            if ctx.guild is not None:
                await ctx.send("Bye!")
                await ctx.guild.leave()
            else:
                await ctx.send("Not possible in DMs.")
        else:
            await guild.leave()
            await ctx.send(f"Left {guild}.")

    @commands.command()
    @commands.is_owner()
    async def loaddata(self, ctx: Context):
        '''Reloads tile data from the world map, editor, and custom files.'''
        self.bot.loading = True
        await self.load_initial_tiles()
        await self.load_editor_tiles()
        await self.load_custom_tiles()
        self.bot.loading = False
        return await ctx.send("Done. Loaded all tile data.")

    async def load_initial_tiles(self):
        '''Loads tile data from `data/values.lua` and `.ld` files.'''
        # values.lua contains the data about which color (on the palette) is associated with each tile.
        with open("data/values.lua", encoding="utf-8", errors="replace") as fp:
            data = fp.read()
        
        start = data.find("tileslist =\n")
        end = data.find("\n}\n", start)

        assert start > 0 and end > 0
        spanned = data[start:end]

        def prepare(d: dict[str, Any]) -> dict[str, Any]:
            '''From game format into DB format'''
            if d.get("type") is not None:
                d["text_type"] = d.pop("type")
            if d.get("image") is not None:
                d["sprite"] = d.pop("image")
            if d.get("colour") is not None:    
                inactive = d.pop("colour").split(",")
                d["inactive_color_x"] = int(inactive[0])
                d["inactive_color_y"] = int(inactive[1])
            if d.get("activecolour") is not None:
                active = d.pop("activecolour").split(",")
                d["active_color_x"] = int(active[0])
                d["active_color_y"] = int(active[1])
            return d

        object_pattern = re.compile(
            r"(object\d+) =\n\t\{"
            r"\n\s*name = \"([^\"]*)\","
            r"\n\s*sprite = \"([^\"]*)\","
            r"\n.*\n.*\n\s*tiling = (-1|\d),"
            r"\n\s*type = (\d),"
            r"\n\s*(?:argextra = .*,\n\s*)?(?:argtype = .*,\n\s*)?"
            r"colour = \{(\d), (\d)\},"
            r"\n\s*(?:active = \{(\d), (\d)\},\n\s*)?"
            r".*\n.*\n.*\n\s*\}",
        )
        initial_objects: dict[str, dict[str, Any]] = {}
        for match in re.finditer(object_pattern, spanned):
            obj, name, sprite, tiling, type, c_x, c_y, a_x, a_y = match.groups()
            if a_x is None or a_y is None:
                inactive_x = active_x = int(c_x)
                inactive_y = active_y = int(c_y)
            else:
                inactive_x = int(c_x)
                inactive_y = int(c_y)
                active_x = int(a_x)
                active_y = int(a_y)
            tiling = int(tiling)
            type = int(type)
            initial_objects[obj] = dict(
                name=name,
                sprite=sprite,
                tiling=tiling,
                text_type=type,
                inactive_color_x=inactive_x,
                inactive_color_y=inactive_y,
                active_color_x=active_x,
                active_color_y=active_y,
            )

        changed_objects: list[dict[str, Any]] = []
        for path in pathlib.Path(f"data/levels/{constants.BABA_WORLD}").glob("*.ld"):

            parser = configparser.ConfigParser()
            parser.read(path, encoding="utf-8")
            changed_ids = parser.get("tiles", "changed", fallback=",").split(",")[:-1]

            fields = ("name", "image", "tiling", "colour", "activecolour", "type")
            for id in changed_ids:
                changes: dict[str, Any] = {}
                for field in fields:
                    change = parser.get("tiles", f"{id}_{field}", fallback=None)
                    if change is not None:
                        changes[field] = change
                # Ignore blank changes (identical to values.lua objects)
                # Ignore changes without a name (the same name but a different color, etc)
                if changes and changes.get("name") is not None:
                    changed_objects.append({**initial_objects[id], **prepare(changes)})
            
        with open("config/editortileignore.json") as f:
            ignored_names = json.load(f)
        by_name = filter(lambda x: x[0] not in ignored_names, itertools.groupby(
            sorted(changed_objects, key=lambda x: x["name"]), 
            key=lambda x: x["name"]
        ))
        ready: list[dict[str, Any]] = []
        for name, duplicates in by_name:
            def freeze_dict(d: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
                '''Hashable (frozen) dict'''
                return tuple(d.items())
            counts = collections.Counter(map(freeze_dict, duplicates))
            most_common, _ = counts.most_common(1)[0]
            ready.append(dict(most_common))
    
        await self.bot.db.conn.executemany(
            f'''
            INSERT INTO tiles(
                name,
                sprite,
                source,
                version,
                inactive_color_x,
                inactive_color_y,
                active_color_x,
                active_color_y,
                tiling,
                text_type
            )
            VALUES (
                :name,
                :sprite,
                {repr(constants.BABA_WORLD)},
                0,
                :inactive_color_x,
                :inactive_color_y,
                :active_color_x,
                :active_color_y,
                :tiling,
                :text_type
            )
            ON CONFLICT(name, version)
            DO UPDATE SET
                sprite=excluded.sprite,
                source={repr(constants.BABA_WORLD)},
                inactive_color_x=excluded.inactive_color_x,
                inactive_color_y=excluded.inactive_color_y,
                active_color_x=excluded.active_color_x,
                active_color_y=excluded.active_color_y,
                tiling=excluded.tiling,
                text_type=excluded.text_type;
            ''',
            initial_objects.values()
        )

        await self.bot.db.conn.executemany(
            f'''
            INSERT INTO tiles
            VALUES (
                :name,
                :sprite,
                {repr(constants.BABA_WORLD)},
                0,
                :inactive_color_x,
                :inactive_color_y,
                :active_color_x,
                :active_color_y,
                :tiling,
                :text_type,
                NULL,
                ""
            ) 
            ON CONFLICT(name, version) DO NOTHING;
            ''',
            ready
        )

    async def load_editor_tiles(self):
        '''Loads tile data from `data/editor_objectlist.lua`.'''

        with open("data/editor_objectlist.lua", encoding="utf-8", errors="replace") as fp:
            data = fp.read()
        
        start = data.find("editor_objlist = {")
        end = data.find("\n}", start)
        assert start > 0 and end > 0
        spanned = data[start:end]

        object_pattern = re.compile(
            r"\[\d+\] = \{"
            r"\n\s*name = \"([^\"]*)\","
            r"(?:\n\s*sprite = \"([^\"]*)\",)?"
            r"\n.*"
            r"\n\s*tags = \{((?:\"[^\"]*?\"(?:,\"[^\"]*?\")*)?)\},"
            r"\n\s*tiling = (-1|\d),"
            r"\n\s*type = (\d),"
            r"\n.*"
            r"\n\s*colour = \{(\d), (\d)\},"
            r"(?:\n\s*colour_active = \{(\d), (\d)\})?"
        )
        tag_pattern = re.compile(r"\"([^\"]*?)\"")
        objects = []
        for match in re.finditer(object_pattern, spanned):
            name, sprite, raw_tags, tiling, text_type, c_x, c_y, a_x, a_y = match.groups()
            sprite = name if sprite is None else sprite
            a_x = c_x if a_x is None else a_x
            a_y = c_y if a_y is None else a_y
            active_x = int(a_x)
            active_y = int(a_y)
            inactive_x = int(c_x)
            inactive_y = int(c_y)
            tiling = int(tiling)
            text_type = int(text_type)
            tag_list = []
            for tag in re.finditer(tag_pattern, raw_tags):
                tag_list.append(tag.group(0))
            tags = "\t".join(tag_list)

            objects.append(dict(
                name=name,
                sprite=sprite,
                tiling=tiling,
                text_type=text_type,
                inactive_color_x=inactive_x,
                inactive_color_y=inactive_y,
                active_color_x=active_x,
                active_color_y=active_y,
                tags=tags
            ))
        
        await self.bot.db.conn.executemany(
            f'''
            INSERT INTO tiles
            VALUES (
                :name,
                :sprite,
                {repr(constants.BABA_WORLD)},
                1,
                :inactive_color_x,
                :inactive_color_y,
                :active_color_x,
                :active_color_y,
                :tiling,
                :text_type,
                NULL,
                :tags
            ) 
            ON CONFLICT(name, version)
            DO UPDATE SET 
                sprite=excluded.sprite,
                source={repr(constants.BABA_WORLD)},
                inactive_color_x=excluded.inactive_color_x,
                inactive_color_y=excluded.inactive_color_y,
                active_color_x=excluded.active_color_x,
                active_color_y=excluded.active_color_y,
                tiling=excluded.tiling,
                text_type=excluded.text_type,
                tags=:tags;
            ''',
            objects
        )

    async def load_custom_tiles(self):
        '''Loads custom tile data from `data/custom/*.json`'''
        def prepare(source: str, d: dict[str, Any]) -> dict[str, Any]:
            '''From config format to db format'''
            inactive = d.pop("color")
            if d.get("active") is not None:
                d["inactive_color_x"] = inactive[0]
                d["inactive_color_y"] = inactive[1]
                d["active_color_x"] = d["active"][0]
                d["active_color_y"] = d["active"][1]
            else:
                d["inactive_color_x"] = d["active_color_x"] = inactive[0]
                d["inactive_color_y"] = d["active_color_y"] = inactive[1]
            d["source"] = d.get("source", source)
            d["tiling"] = d.get("tiling", -1)
            d["text_type"] = d.get("text_type", 0)
            d["text_direction"] = d.get("text_direction")
            d["tags"] = d.get("tags", "")
            return d

        async with self.bot.db.conn.cursor() as cur:
            for path in pathlib.Path("data/custom").glob("*.json"):
                source = path.parts[-1].split(".")[0]
                with open(path, errors="replace", encoding="utf-8") as fp:
                    objects = [prepare(source, obj) for obj in json.load(fp)]
                
                await cur.executemany(
                    '''
                    INSERT INTO tiles
                    VALUES (
                        :name,
                        :sprite,
                        :source,
                        2,
                        :inactive_color_x,
                        :inactive_color_y,
                        :active_color_x,
                        :active_color_y,
                        :tiling,
                        :text_type,
                        :text_direction,
                        :tags
                    ) 
                    ON CONFLICT(name, version)
                    DO UPDATE SET 
                        sprite=excluded.sprite,
                        source=excluded.source,
                        inactive_color_x=excluded.inactive_color_x,
                        inactive_color_y=excluded.inactive_color_y,
                        active_color_x=excluded.active_color_x,
                        active_color_y=excluded.active_color_y,
                        tiling=excluded.tiling,
                        text_type=excluded.text_type,
                        text_direction=excluded.text_direction,
                        tags=excluded.tags;
                    ''',
                    objects
                )
                # this is a mega HACK, but I'm keeping it because the alternative is a headache
                hacks = [x for x in objects if "baba_special" in x["tags"].split("\t")]
                await cur.executemany(
                    '''
                    INSERT INTO tiles
                    VALUES (
                        :name,
                        :sprite,
                        :source,
                        0,
                        :inactive_color_x,
                        :inactive_color_y,
                        :active_color_x,
                        :active_color_y,
                        :tiling,
                        :text_type,
                        :text_direction,
                        :tags
                    ) 
                    ON CONFLICT(name, version)
                    DO UPDATE SET 
                        sprite=excluded.sprite,
                        source=excluded.source,
                        inactive_color_x=excluded.inactive_color_x,
                        inactive_color_y=excluded.inactive_color_y,
                        active_color_x=excluded.active_color_x,
                        active_color_y=excluded.active_color_y,
                        tiling=excluded.tiling,
                        text_type=excluded.text_type,
                        text_direction=excluded.text_direction,
                        tags=excluded.tags;
                    ''',
                    hacks
                )

    @commands.command()
    @commands.is_owner()
    async def hidden(self, ctx: Context):
        '''Lists all hidden commands.'''
        cmds = "\n".join([cmd.name for cmd in self.bot.commands if cmd.hidden])
        await ctx.send(f"All hidden commands:\n{cmds}")

    @commands.command()
    @commands.is_owner()
    async def doc(self, ctx: Context, command: commands.Command):
        '''Check a command's docstring.'''
        help = command.help
        await ctx.send(f"Command doc for {command}:\n{help}")

    @commands.command()
    @commands.is_owner()
    async def sql(self, ctx: Context, *, query: str):
        '''Run some sql'''
        async with self.bot.db.conn.cursor() as cur:
            await cur.execute(query)
            rows = await cur.fetchall()
        formatted = '\n'.join('|'.join(str(value) for value in row) for row in rows)
        out = f"Output:\n```\n{formatted}\n```"
        await ctx.send(out)

    @commands.command()
    @commands.is_owner()
    async def loadletters(self, ctx: Context):
        '''Scrapes individual letters from vanilla sprites.'''
        ignored = json.load(open("config/letterignore.json"))
        for row in await self.bot.db.conn.fetchall(
            f'''
            SELECT * FROM tiles
            WHERE sprite LIKE "text\\___%" ESCAPE "\\"
                AND source == {repr(constants.BABA_WORLD)}
                AND text_direction IS NULL;
            '''
        ):
            data = TileData.from_row(row)
            if data.sprite not in ignored:
                await self.load_letter(
                    data.sprite, 
                    data.text_type # type: ignore
                )

        await self.load_ready_letters()

        await ctx.send("Letters loaded.")

    async def load_letter(self, word: str, tile_type: int):
        '''Scrapes letters from a sprite.'''
        chars = word[5:] # Strip "text_" prefix

        # Get the number of rows
        two_rows = len(chars) >= 4

        # Background plates for type-2 text,
        # in 1 bit per pixel depth
        plates = [self.bot.db.plate(None, i)[0].getchannel("A").convert("1") for i in range(3)]
        
        # Maps each character to three bounding boxes + images
        # (One box + image for each frame of animation)
        # char_pos : [((x1, y1, x2, y2), Image), ...]
        char_sizes: dict[tuple[int, str], Any] = {}
        
        # Scrape the sprites for the sprite characters in each of the three frames
        for i, plate in enumerate(plates):
            # Get the alpha channel in 1-bit depth
            alpha = Image.open(f"data/sprites/{constants.BABA_WORLD}/{word}_0_{i + 1}.png") \
                .convert("RGBA") \
                .getchannel("A") \
                .convert("1")
            
            # Type-2 text has inverted text on a background plate
            if tile_type == 2:
                alpha = ImageChops.invert(alpha)
                alpha = ImageChops.logical_and(alpha, plate)


            # Get the point from which characters are seeked for
            x = 0
            y = 6 if two_rows else 12

            # Flags
            skip = False
            
            # More than 1 bit per pixel is required for the flood fill
            alpha = alpha.convert("L")
            for i, char in enumerate(chars):
                if skip:
                    skip = False
                    continue

                while alpha.getpixel((x, y)) == 0:
                    if x == alpha.width - 1:
                        if two_rows and y == 6:
                            x = 0
                            y = 18
                        else:
                            break
                    else:
                        x += 1
                # There's a letter at this position
                else:
                    clone = alpha.copy()
                    ImageDraw.floodfill(clone, (x, y), 128) # 1 placeholder
                    clone = Image.eval(clone, lambda x: 255 if x == 128 else 0)
                    clone = clone.convert("1")
                    
                    # Get bounds of character blob 
                    x1, y1, x2, y2 = clone.getbbox() # type: ignore
                    # Run some checks
                    # # Too wide => Skip 2 characters (probably merged two chars)
                    # if x2 - x1 > (1.5 * alpha.width * (1 + two_rows) / len(chars)):
                    #     skip = True
                    #     alpha = ImageChops.difference(alpha, clone)
                    #     continue
                    
                    # Too tall? Scrap the rest of the characters
                    if y2 - y1 > 1.5 * alpha.height / (1 + two_rows):
                        break

                    # too thin! bad letter.
                    if x2 - x1 <= 2:
                        alpha = ImageChops.difference(alpha, clone)
                        continue
                    
                    # Remove character from sprite, push to char_sizes
                    alpha = ImageChops.difference(alpha, clone)
                    clone = clone.crop((x1, y1, x2, y2))
                    entry = ((x1, y1, x2, y2), clone)
                    char_sizes.setdefault((i, char), []).append(entry)
                    continue
                return

        results = []
        for (_, char), entries in char_sizes.items():
            # All three frames clearly found the character in the sprite
            if len(entries) == 3:
                x1_min = min(entries, key=lambda x: x[0][0])[0][0]
                y1_min = min(entries, key=lambda x: x[0][1])[0][1]
                x2_max = max(entries, key=lambda x: x[0][2])[0][2]
                y2_max = max(entries, key=lambda x: x[0][3])[0][3]

                blobs = []
                mode = "small" if two_rows else "big"
                width = 0
                height = 0
                for i, ((x1, y1, _, _), img) in enumerate(entries):
                    frame = Image.new("1", (x2_max - x1_min, y2_max - y1_min))
                    frame.paste(img, (x1 - x1_min, y1 - y1_min))
                    width, height = frame.size
                    buf = BytesIO()
                    frame.save(buf, format="PNG")
                    blobs.append(buf.getvalue())
                results.append((mode, char, width, *blobs))

        await self.bot.db.conn.executemany(
            '''
            INSERT INTO letters
            VALUES (?, ?, ?, ?, ?, ?);
            ''',
            results
        )   

    async def load_ready_letters(self):
        def channel_shenanigans(im: Image.Image) -> Image.Image:
            if im.mode == "1":
                return im
            elif im.mode == "RGB" or im.mode == "L":
                return im.convert("1")
            return im.convert("RGBA").getchannel("A").convert("1")
        data = []
        for path in pathlib.Path("data/letters").glob("*/*/*/*_0.png"):
            _, _, mode, char, w, name = path.parts
            char = char.replace("asterisk", "*")
            width = int(w)
            prefix = name[:-6]
            # mo ch w h
            buf_0 = BytesIO()
            channel_shenanigans(Image.open(path)).save(buf_0, format="PNG")
            blob_0 = buf_0.getvalue()
            buf_1 = BytesIO()
            channel_shenanigans(Image.open(path.parent / f"{prefix}_1.png")).save(buf_1, format="PNG")
            blob_1 = buf_1.getvalue()
            buf_2 = BytesIO()
            channel_shenanigans(Image.open(path.parent / f"{prefix}_2.png")).save(buf_2, format="PNG")
            blob_2 = buf_2.getvalue()
            data.append((mode, char, width, blob_0, blob_1, blob_2))

        await self.bot.db.conn.executemany(
            '''
            INSERT INTO letters
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            data
        )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await self.bot.db.conn.execute(
            '''
            DELETE FROM guilds WHERE guild_id = ?;
            ''',
            guild.id
        )

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if len(self.bot.guilds) > constants.MAXIMUM_GUILD_THRESHOLD:
            # urgent
            await guild.leave()
            return
        
        bots = await self.bot.db.conn.fetchall(
            '''
            SELECT COUNT(*) FROM guilds WHERE guild_id = ?;
            ''',
            guild.id
        )
        if bots[0][0] != 0:
            for channel in guild.text_channels:
                try:
                    await channel.send("Please kick the other @ROBOT IS YOU bots first.")
                except:
                    continue
                else:
                    break
            await guild.leave()
            return

        await self.bot.db.conn.execute(
            '''
            INSERT INTO guilds VALUES (?, ?);
            ''',
            guild.id, self.bot.user.id
        )

        webhook = discord.Webhook.from_url(self.bot.webhook_url, adapter=discord.AsyncWebhookAdapter(self.bot.session))
        embed = discord.Embed(
            color = self.bot.embed_color,
            title = f"Instance {self.bot.instance_id}: {self.bot.user} Joined Guild",
            description = f"Joined {guild.name} (guild #{len(self.bot.guilds)})."
        )
        embed.add_field(name="ID", value=str(guild.id))
        embed.add_field(name="Member Count", value=str(guild.member_count))
        await webhook.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def debug(self, ctx: Context):
        '''Return some debug stats for instances.'''
        bots = await self.bot.db.conn.fetchall(
            '''
            SELECT counts.bot_id, (
                SELECT COUNT(*) FROM guilds WHERE bot_id == counts.bot_id
            ) as count
            FROM guilds AS counts
            GROUP BY counts.bot_id
            ORDER BY count ASC;
            '''
        )
        out = [
            "Guild counts:"
        ]
        for row in bots:
            out.append(f"[{row[0]}]: {row[1]}")
        await ctx.send("\n".join(out))

    @commands.command(aliases=["previewzip", "showzip"])
    @commands.is_owner()
    async def viewzip(self, ctx: Context):
        '''Preview the file names of the zip'''
        files = zipfile.ZipFile(BytesIO(await ctx.message.attachments[0].read())).namelist()
        files.sort()
        names = "\n".join(files)
        await ctx.send(f"```\n{names}```")

    @commands.command()
    @commands.is_owner()
    async def addsprite(self, ctx: Context, pack_name: str, color_x: int = 0, color_y: int = 3, tiling: int = -1):
        '''Adds sprites to a specified sprite pack'''
        zip = zipfile.ZipFile(BytesIO(await ctx.message.attachments[0].read()))
        sprite_name = re.match(r'(?:.+/)?(.+?)(?:\_\d)*\.png', zip.namelist()[0]).groups()[0]   
        if not os.path.isdir(f"data/sprites/{pack_name}") or not os.path.isfile(f"data/custom/{pack_name}.json"):
            return await ctx.error(f"Pack {pack_name} doesn't exist.")
        for name in zip.namelist():
            sprite = zip.read(name)
            path = name.split("/")[-1]
            with open(f"data/sprites/{pack_name}/{path}", "wb") as f:
                f.write(sprite)
        with open(f"data/custom/{pack_name}.json", "r") as f:
            sprite_data = json.load(f)
        sprite_data.append({
            "name": sprite_name,
            "sprite": sprite_name,
            "color": [
                str(color_x),
                str(color_y)
            ],
            "tiling": str(tiling)
        })
        with open(f"data/custom/{pack_name}.json", "w") as f:
            json.dump(sprite_data, f, indent=4)
        await ctx.send(f"Added {sprite_name}.")

    @commands.command()
    @commands.is_owner()
    async def addpack(self, ctx: Context, short_name: str, long_name: str, version: str, author: str):
        '''Registers a custom levelpack!'''
        zip = zipfile.ZipFile(BytesIO(await ctx.message.attachments[0].read()))
        os.makedirs(f"data/levels/{short_name}", exist_ok=True)
        os.makedirs(f"data/sprites/{short_name}", exist_ok=True)
        os.makedirs(f"data/images/{short_name}", exist_ok=True)
        for file_name in zip.namelist():
            path = pathlib.Path(file_name)
            if len(path.parts) == 2:
                _, name = path.parts
                if name.endswith(".l") or name.endswith(".ld"):
                    level = zip.read(file_name)
                    with open(f"data/levels/{short_name}/{name}", "wb") as f:
                        f.write(level)
            elif len(path.parts) == 3:
                _, folder, *_, name = path.parts
                if folder.lower() == "palettes":
                    if name.endswith(".png"):
                        palette = zip.read(file_name)
                        with open(f"data/palettes/{name}", "wb") as f:
                            f.write(palette)
                elif folder.lower() == "sprites":
                    if name.endswith(".png"):
                        sprite = zip.read(file_name)
                        with open(f"data/sprites/{short_name}/{name}", "wb") as f:
                            f.write(sprite)
                elif folder.lower() == "images":
                    if name.endswith(".png"):
                        sprite = zip.read(file_name)
                        with open(f"data/images/{short_name}/{name}", "wb") as f:
                            f.write(sprite)
        with open("data/levelpacks.json") as f:
            packs = json.load(f)
            packs[short_name] = {
                "version": version,
                "name": long_name,
                "author": author
            }
        with open("data/levelpacks.json", "w") as f:
            json.dump(packs, f)
        await ctx.send(f"Added `{long_name}` (`{short_name}`) `{version}` by `{author}`.")

def setup(bot: Bot):
    bot.add_cog(OwnerCog(bot))
