import discord
from discord.ext import commands
from json import load

emoteFile = open("emotecache.json")
emoteCache = load(emoteFile)
emoteFile.close()


class globalCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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
            for row in wordGrid:
                emoteRow = []
                for word in row:
                    emote = emoteCache.get(word)
                    if emote == None:
                        failedWord = word
                        raise ValueError
                    else:
                        emoteRow.append(emote)
                emoteGrid.append(emoteRow)
        except ValueError:
            await ctx.send("⚠️ Could not find a tile for \"%s\"." % failedWord)
        
        responseRows = [" ".join(row) for row in emoteGrid]
        responseMessage = "\n".join(responseRows)
        await ctx.send(responseMessage)
        

def setup(bot):
    bot.add_cog(globalCog(bot))

