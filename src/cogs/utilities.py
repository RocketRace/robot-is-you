from __future__ import annotations
import discord
import re
from datetime    import datetime
from discord.ext import commands
from os          import listdir
from src.utils   import constants

class UtilityCommandsCog(commands.Cog, name="Utility Commands"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    @commands.cooldown(5, 8, type=commands.BucketType.channel)
    async def search(self, ctx, *, query: str):
        '''Searches for tiles based on a query.

        **You may use these flags to navigate the output:**
        * `page`: Which page of output you wish to view. (Example usage: `search text page:2`)
        * `sort`: Which value to sort by. Defaults to `name`.
        * `reverse`: Whether or not the output should be in descending order or not. This may be `true` or `false`.

        **Queries may contain the following flags to filter results.**
        * `sprite`: The name of the sprite. Will return only tiles that use that sprite.
        * `text`: May be `true` or `false`. With `true`, this will only return text tiles.
        * `source`: The source of the sprite. Valid values for this are `vanilla`, `vanilla-extensions`, `cg5-mods`, `lily-and-patashu-mods`, `patasuhu-redux`, `misc`, and `modded`. Using `modded` will return any non-vanilla tiles.
        * `color`: The color index of the sprite. Must be two positive integers. Example: `1,2`
        * `tiling`: The tiling type of the object. This must be either `-1` (non-tiling objects), `0` (directional objects), `1` (tiling objects), `2` (character objects), `3` (directional & animated objects) or `4` (animated objects). 

        **Example commands:**
        `search baba`
        `search text:false source:vanilla sta`
        `search source:modded sort:color page:4`
        `search text:true color:0,3 reverse:true`
        '''
        sanitized_query = discord.utils.escape_mentions(query)
        # Pattern to match flags in the format (flag):(value)
        flag_pattern = r"([\d\w_]+):([\d\w,-_]+)"
        match = re.search(flag_pattern, query)
        plain_query = ""

        # Whether or not to use simple string matching
        has_flags = bool(match)
        
        # Determine which flags to filter with
        flags = {}
        if has_flags:
            if match:
                flags = dict(re.findall(flag_pattern, query)) # Returns "flag":"value" pairs
            # Nasty regex to match words that are not flags
            non_flag_pattern = r"(?<![:\w\d,-])([\w\d,_]+)(?![:\d\w,-])"
            plain_match = re.findall(non_flag_pattern, query)
            plain_query = " ".join(plain_match)
        
        # Which value to sort output by
        sort_by = "name"
        secondary_sort_by = "name" # This is constant
        if flags.get("sort") is not None:
            sort_by = flags["sort"]
            flags.pop("sort")
        
        reverse = False
        reverse_flag = flags.get("reverse")
        if reverse_flag is not None and reverse_flag.lower() == "true":
            reverse = True
            flags.pop("reverse")

        page = 0
        page_flag = flags.get("page")
        if page_flag is not None and page_flag.isnumeric():
            page = int(flags["page"]) - 1
            flags.pop("page")

        # How many results will be shown
        limit = 20
        results = 0
        matches = []

       # Searches through a list of the names of each tile
        data = self.bot.get_cog("Admin").tile_data
        for name,tile in data.items():
            if has_flags:
                # Checks if the object matches all the flag parameters
                passed = {f:False for f,v in flags.items()}
                # Process flags for one object
                for flag,value in flags.items():
                    # Object name starts with "text_"
                    if flag.lower() == "text":
                        
                        if value.lower() == "true":
                            if name.startswith("text_"): passed[flag] = True

                        elif value.lower() == "false":
                            if not name.startswith("text_"): passed[flag] = True
                    
                    # Object source is vanilla, modded or (specific mod)
                    elif flag == "source":
                        if value.lower() == "modded":
                            if tile["source"] not in ["vanilla", "vanilla-extensions"]:
                                passed[flag] = True
                        else:
                            if tile["source"] == value.lower():
                                passed[flag] = True

                    # Object uses a specific color index ("x,y" is parsed to ["x", "y"])
                    elif flag == "color":
                        index = value.lower().split(",")
                        if tile["color"] == index:
                            passed[flag] = True

                    # For all other flags: Check that the specified object attribute has a certain value
                    else:  
                        if tile.get(flag) == value.lower():
                            passed[flag] = True
                
                # If we pass all flags (and there are more than 0 passed flags)
                if has_flags and all(passed.values()):
                    if plain_query in name:
                        results += 1
                        # Add our object to our results, and append its name (originally a key)
                        obj = tile
                        obj["name"] = name
                        matches.append(obj)

            # If we have no flags, simply use a substring search
            else:
                if query in name:
                    results += 1
                    obj = tile
                    obj["name"] = name
                    matches.append(obj)

        # Determine our output pagination
        first_result = page * limit
        last_result = (page + 1) * limit
        # Some sanitization to avoid negative indices
        if first_result < 0: 
            first_result = 0
        if last_result < 0:
            last_result = limit
        # If we try to go over the limit, just show the last page
        last_page = results // limit
        if first_result > results:
            first_result = last_page
        if last_result > results:
            last_result = results - 1
        
        # What message to prefix our output with
        if results == 0:
            matches.insert(0, f"Found no results for \"{sanitized_query}\".")
        elif results > limit:
            matches.insert(0, f"Found {results} results using query \"{sanitized_query}\". Showing page {page + 1} of {last_page + 1}:")
        else:
            matches.insert(0, f"Found {results} results using query \"{sanitized_query}\":")
        
        # Tidy up our output with this mess
        content = "\n".join([f"**{x.get('name')}** : {', '.join([f'{k}: `{v[0]},{v[1]}`' if isinstance(v, list) else f'{k}: `{v}`' for k, v in sorted(x.items(), key=lambda λ: λ[0]) if k not in ['name', 'tags']])}" if not isinstance(x, str) else x for x in [matches[0]] + sorted(matches[1:], key=lambda λ: (λ[sort_by], λ[secondary_sort_by]), reverse=reverse)[first_result:last_result + 1]])
        await self.bot.send(ctx, content)

    @commands.cooldown(5, 8, type=commands.BucketType.channel)
    @commands.command(name="list")
    async def list_tiles(self, ctx):
        '''Lists valid tiles for rendering.

        Returns all valid tiles in a text file.
        Tiles may be used in the `tile` (and subsequently `rule`) commands.
        '''
        now = datetime.now().strftime("%Y-%m-%d")
        fp = discord.File("target/tilelist.txt", filename=f"tilelist_{now}.txt")
        await ctx.send( "List of all valid tiles:", file=fp)

    @commands.cooldown(5, 8, type=commands.BucketType.channel)
    @commands.command(name="palettes")
    async def list_palettes(self, ctx):
        '''Lists palettes usable for rendering.

        Palettes can be used as arguments for the `tile` (and subsequently `rule`) commands.
        '''
        msg = []
        for palette in listdir("data/palettes"):
            if not palette in [".DS_Store"]:
                msg.append(palette[:-4])
        msg.sort()
        msg.insert(0, "Valid palettes:")
        await self.bot.send(ctx, "\n".join(msg))

    @commands.cooldown(5, 8, type=commands.BucketType.channel)
    @commands.command(name="variants")
    async def list_variants(self, ctx, tile):
        '''List valid sprite variants for a given tile.'''
        # Clean the input
        clean_tile = tile.strip().lower()

        # Does the tile exist?
        data = self.bot.get_cog("Admin").tile_data.get(clean_tile)
        suffix = "It also supports the following colors:\n" + \
            ", ".join(f"`:{name}`" for name in constants.valid_colors) + \
            ",\nas well as the following filters:\n`:meta` / `:m`, :m2`, `:m3`, `:hide`."
        if data is None:
            output = [
                f"This tile doesn't exist, but you might be able to auto-generate the text tile `text_{clean_tile}`.",
                "Auto-generated text supports the `:noun`, `:letter`, and `:property` variants.",
                suffix
            ]
            return await self.bot.send(ctx, f"Valid sprite variants for '{clean_tile}'\n" + "\n".join(output) + "\n")
        
        # Determines the tiling type of the tile
        tiling = data.get("tiling")

        # Possible tiling types and the corresponding available variants
        output = {
            None: [
                "This tile does not exist, or has no tiling data."
            ],
            "-1": [
                "This tile has no sprite variants.",
            ],
            "0": [
                "This tile supports directions:",
                "Facing right: `:right` / `:r`",
                "Facing up: `:up` / `:u`",
                "Facing left: `:left` / `:l`",
                "Facing down: `:down` / `:d`",
                "You can also provide raw variants from `:0` to `:31` to alter its sprite. (Not all are valid.)"
            ],
            "1": [
                "This is a tiling tile. It automatically applies sprite variants to itself.",
                "You can provide raw variants from `:0` to `:15` to alter its sprite."
            ],
            "2": [
                "This tile supports direction, animations, and sleeping sprites:",
                "Sleeping (ANY DIRECTION): `:sleep` / `:s`",
                "Animation frame (ANY DIRECTION): `:a0`, `:a1`, `:a2`, `:a3`",
                "Facing right: `:right` / `:r`",
                "Facing up: `:up` / `:u`",
                "Facing left: `:left` / `:l`",
                "Facing down: `:down` / `:d`",
                "You can also provide raw variants from `:0` to `:31` to alter its sprite. (Not all are valid.)"
            ],
            "3": [
                "This tile supports directions and animations:",
                "Animation frame (ANY DIRECTION): `:a0`, `:a1`, `:a2`, `:a3`",
                "Facing right: `:right` / `:r`",
                "Facing up: `:up` / `:u`",
                "Facing left: `:left` / `:l`",
                "Facing down: `:down` / `:d`",
                "You can also provide raw variants from `:0` to `:31` to alter its sprite. (Not all are valid.)"
            ],
            "4": [
                "This tile supports animations:",
                "Animation frame (ANY DIRECTION): `:a0`, `:a1`, `:a2`, `:a3`",
                "You can also provide raw variants from `:0` to `:31` to alter its sprite. (Not all are valid.)"
            ]
        }
        choice = output[tiling]
        if clean_tile.startswith("text_"):
            choice.append("It can also be auto-generated, supporting the `:noun`, `:letter`, and `:property` variants.",)
        choice.append(suffix)

        # Output
        await self.bot.send(ctx, f"Valid sprite variants for '{clean_tile}'\n" + "\n".join(choice) + "\n")


def setup(bot: commands.Bot):
    bot.add_cog(UtilityCommandsCog(bot))
