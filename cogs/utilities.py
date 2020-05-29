import discord
import re
from datetime    import datetime
from discord.ext import commands
from os          import listdir

class UtilityCommandsCog(commands.Cog, name="Utility Commands"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.cooldown(2, 5, type=commands.BucketType.channel)
    async def search(self, ctx, *, query: str):
        '''
        Searches for tiles based on a query.

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
        sanitizedQuery = discord.utils.escape_mentions(query)
        # Pattern to match flags in the format (flag):(value)
        flagPattern = r"([\d\w_]+):([\d\w,-_]+)"
        match = re.search(flagPattern, query)
        plainQuery = ""

        # Whether or not to use simple string matching
        hasFlags = bool(match)
        
        # Determine which flags to filter with
        flags = {}
        if hasFlags:
            if match:
                flags = dict(re.findall(flagPattern, query)) # Returns "flag":"value" pairs
            # Nasty regex to match words that are not flags
            nonFlagPattern = r"(?<![:\w\d,-])([\w\d,_]+)(?![:\d\w,-])"
            plainMatch = re.findall(nonFlagPattern, query)
            plainQuery = " ".join(plainMatch)
        
        # Which value to sort output by
        sortBy = "name"
        secondarySortBy = "name" # This is constant
        if flags.get("sort") is not None:
            sortBy = flags["sort"]
            flags.pop("sort")
        
        reverse = False
        reverseFlag = flags.get("reverse")
        if reverseFlag is not None and reverseFlag.lower() == "true":
            reverse = True
            flags.pop("reverse")

        page = 0
        pageFlag = flags.get("page")
        if pageFlag is not None and pageFlag.isnumeric():
            page = int(flags["page"]) - 1
            flags.pop("page")

        # How many results will be shown
        limit = 20
        results = 0
        matches = []

       # Searches through a list of the names of each tile
        data = self.bot.get_cog("Admin").tileData
        for name,tile in data.items():
            if hasFlags:
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
                if hasFlags and all(passed.values()):
                    if plainQuery in name:
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
        firstResult = page * limit
        lastResult = (page + 1) * limit
        # Some sanitization to avoid negative indices
        if firstResult < 0: 
            firstResult = 0
        if lastResult < 0:
            lastResult = limit
        # If we try to go over the limit, just show the last page
        lastPage = results // limit
        if firstResult > results:
            firstResult = lastPage
        if lastResult > results:
            lastResult = results - 1
        
        # What message to prefix our output with
        if results == 0:
            matches.insert(0, f"Found no results for \"{sanitizedQuery}\".")
        elif results > limit:
            matches.insert(0, f"Found {results} results using query \"{sanitizedQuery}\". Showing page {page + 1} of {lastPage + 1}:")
        else:
            matches.insert(0, f"Found {results} results using query \"{sanitizedQuery}\":")
        
        # Tidy up our output with this mess
        content = "\n".join([f"**{x.get('name')}** : {', '.join([f'{k}: `{v[0]},{v[1]}`' if isinstance(v, list) else f'{k}: `{v}`' for k, v in sorted(x.items(), key=lambda λ: λ[0]) if k not in ['name', 'tags']])}" if not isinstance(x, str) else x for x in [matches[0]] + sorted(matches[1:], key=lambda λ: (λ[sortBy], λ[secondarySortBy]), reverse=reverse)[firstResult:lastResult + 1]])
        await self.bot.send(ctx, content)

    @commands.cooldown(2, 5, type=commands.BucketType.channel)
    @commands.command(name="list")
    async def listTiles(self, ctx):
        '''
        Lists valid tiles for rendering.
        Returns all valid tiles in a text file.
        Tiles may be used in the `tile` (and subsequently `rule`) commands.
        '''
        now = datetime.now().strftime("%Y-%m-%d")
        fp = discord.File("tilelist.txt", filename=f"tilelist_{now}.txt")
        await ctx.send( "List of all valid tiles:", file=fp)

    @commands.cooldown(2, 5, type=commands.BucketType.channel)
    @commands.command(name="palettes")
    async def listPalettes(self, ctx):
        '''
        Lists palettes usable for rendering.
        Palettes can be used as arguments for the `tile` (and subsequently `rule`) commands.
        '''
        msg = []
        for palette in listdir("palettes"):
            if not palette in [".DS_Store"]:
                msg.append(palette[:-4])
        msg.sort()
        msg.insert(0, "Valid palettes:")
        await self.bot.send(ctx, "\n".join(msg))

    @commands.cooldown(2, 5, type=commands.BucketType.channel)
    @commands.command(name="variants")
    async def listVariants(self, ctx, tile):
        '''
        List valid sprite variants for a given tile.
        '''
        # Clean the input
        cleanTile = tile.strip().lower()

        # Does the tile exist?
        data = self.bot.get_cog("Admin").tileData.get(cleanTile)
        if data is None:
            return await self.bot.error(ctx, f"Could not find a tile with name '{cleanTile}'.")
        
        # Determines the tiling type of the tile
        tiling = data.get("tiling")

        # Possible tiling types and the corresponding available variants
        output = {
            None: [
                "This tile does not exist, or has no tiling data."
            ],
            "-1": [
                "This tile has no extra variants. It supports:",
                "Facing right: `:0` / `:right` / `:r`"
            ],
            "0": [
                "This is a directional tile. It supports:",
                "Facing right: `:0` / `:right` / `:r`",
                "Facing down: `:8` / `:down` / `:d`",
                "Facing left: `:16` / `:left` / `:l`",
                "Facing up: `:24` / `:up` / `:u`",
            ],
            "1": [
                "This is a tiling tile. It automatically applies sprite variants to itself.",
            ],
            "2": [
                "This is a character tile. It supports directional and animated sprites, as well as sleeping sprites:",
                "Facing right: `:0` / `:right` / `:r`",
                "Facing right (alt): `:1`",
                "Facing right (alt): `:2`",
                "Facing right (alt): `:3`",
                "Facing down (sleep): `:7` / `:ds`",
                "Facing down: `:8` / `:down` / `:d`",
                "Facing down (alt): `:9`",
                "Facing down (alt): `:10`",
                "Facing down (alt): `:11`",
                "Facing left (sleep): `:15` / `:ls`",
                "Facing left: `:16` / `:left` / `:l`",
                "Facing left (alt): `:17`",
                "Facing left (alt): `:18`",
                "Facing left (alt): `:19`",
                "Facing up (sleep): `:23` / `:us`",
                "Facing up: `:24` / `:up` / `:u`",
                "Facing up (alt): `:25`",
                "Facing up (alt): `:26`",
                "Facing up (alt): `:27`",
                "Facing right (sleep): `:31` / `:sleep` / `rs`",
            ],
            "3": [
                "This is an animated & directional tile. It supports:",
                "Facing right: `:0` / `:right` / `:r`",
                "Facing right (alt): `:1`",
                "Facing right (alt): `:2`",
                "Facing right (alt): `:3`",
                "Facing down: `:8` / `:down` / `:d`",
                "Facing down (alt): `:9`",
                "Facing down (alt): `:10`",
                "Facing down (alt): `:11`",
                "Facing left: `:16` / `:left` / `:l`",
                "Facing left (alt): `:17`",
                "Facing left (alt): `:18`",
                "Facing left (alt): `:19`",
                "Facing up: `:24` / `:up` / `:u`",
                "Facing up (alt): `:25`",
                "Facing up (alt): `:26`",
                "Facing up (alt): `:27`",
            ],
            "4": [
                "This is an animated tile. It supports:",
                "Facing right: `:0` / `:right` / `:r`",
                "Facing right (alt): `:1`",
                "Facing right (alt): `:2`",
                "Facing right (alt): `:3`",
            ]
        }

        # Output
        await self.bot.send(ctx, f"Valid sprite variants for '{cleanTile}'\n" + "\n".join(output[tiling]) + "\n")


def setup(bot):
    bot.add_cog(UtilityCommandsCog(bot))
