# About

A fun Discord bot based on the indie game [Baba Is You](https://store.steampowered.com/app/736260/Baba_Is_You/) (by Arvi Teikari). This bot was written with the [discord.py](https://discordpy.readthedocs.io/en/latest/) library for Python 3.x.

# Functionality

A list of all commands can be seen using the `help` command. (By default, the bot has a prefix of `+`.)

This bot primarily features rendering and animation of
tiles in *Baba Is You* (through the `tile` and `rule` commands), 
as well as *Baba Is You* levels (using the `level` command).

*Example command:*

![Example command](https://cdn.discordapp.com/attachments/420095557231443988/596606587800387594/unknown.png)

*Example output:*

![Example command output](https://cdn.discordapp.com/attachments/420095557231443988/596606636215500816/unknown.png)

**NOTE: Output is in the form of an animated gif. Try the commands yourself for the best experience.**

# Invite

[Invite the bot to your server!](https://discordapp.com/api/oauth2/authorize?client_id=480227663047294987&scope=bot&permissions=388160)

# Support server

Leave any suggestions, bug reports or questions in the official [support Discord server](https://discord.gg/rMX3YPK).

# To Host This Yourself

Please follow the terms of the license!

Install the requirements: `pip install -r requirements.txt`.

Bot configuration is in `config/setup.json`. It contains the following fields:

* `auth_file` Should point to a JSON file with a `token` field with your bot token.
* `activity` A "playing" message to set at login.
* `description` A description to use in the help command.
* `prefixes` A list of strings that can be used to trigger commands.
* `trigger_on_mention` A boolean dictating whether bot @mentions will behave as a command prefix.
* `webhook_id` The ID of a webhook to report command errors to. Requires the `manage webhooks` permission in the webhook's channel.
* `owner_id` The ID of the bot owner.
* `embed_color` The color of embedded messages.
* `log_file` The file to report logs to.
* `cogs` A list of strings -- cogs to load into the bot.


Run the bot using `python3 ROBOT.py`.

If the bot complains about missing files in `cache/`, create them.

The bot will not work properly on Windows, as it makes use of some unix-ish shell commands.

To load tile data, run the `loaddata` command. To load letter data (for custom text), run the `loadletters` command. To load and pre-render levels, run the `loadlevel` command.
