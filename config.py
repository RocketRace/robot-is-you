import discord

activity = "ROBOT IS HELP"
description = "*An entertainment bot for rendering levels and custom scenes based on the indie game Baba Is You.*"
prefixes = ["+", "Robot is ", "robot is ", "ROBOT IS "]
trigger_on_mention = True
webhook_id = 594692503014473729
embed_color = discord.Color(9077635)
auth_file = "config/auth.json"
log_file = "log.txt"
db_path = "robot.db"
cogs = [
    "src.cogs.owner",
    "src.cogs.global",
    "src.cogs.meta",
    "src.cogs.errorhandler",
    "src.cogs.reader",
    "src.cogs.render",
    "src.cogs.variants",
    "src.cogs.utilities",
    "jishaku"
]
