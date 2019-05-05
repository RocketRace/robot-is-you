import discord
from json        import load
from discord.ext import commands

class globalCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        emoteFile = open("emotecache.json")
        self.emoteCache = load(emoteFile)
        emoteFile.close()

    # The rule command only uses text tiles, saving some convenience from the user but gating some emotes away
    # If you want the bot to return other tiles, use the tile command
    @commands.command(name="rule")
    @commands.guild_only()
    async def rule(self, ctx, *, content: str):
        wordRows = content.lower().splitlines()
        wordGrid = [row.split() for row in wordRows]
        emoteGrid = []
        failedWord = ""

        # Gets the associated emote text from emoteCache for each word in the input
        # Throws an exception which sends an error message if a word is not found.
        try:
            # Each row
            for row in wordGrid:
                emoteRow = []
                # Each word
                for word in row:
                    # Checks for the word in the cache
                    emote = self.emoteCache.get("text_" + word)
                    # If not present, fails...
                    if emote == None:
                        failedWord = word
                        raise ValueError
                    else:
                        emoteRow.append(emote)
                emoteGrid.append(emoteRow)
        # ... and sends an error message
        except ValueError:
            await ctx.send("⚠️ Could not find a tile for \"%s\"." % failedWord)
        
        # Joins the emotes on each row
        responseRows = [" ".join(row) for row in emoteGrid]
        # Joins each row
        responseMessage = "\n".join(responseRows)
        # Tests for character limits
        if len(responseMessage) > 2000:
            await ctx.send("```\n🚫Message is over 2000 characters long.\n```")
        else:
            await ctx.send(responseMessage)
        
def setup(bot):
    bot.add_cog(globalCog(bot))

