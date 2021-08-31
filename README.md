# About

A fun Discord bot based on the indie game [Baba Is You](https://store.steampowered.com/app/736260/Baba_Is_You/) (by Arvi Teikari). This bot was written with the [discord.py](https://discordpy.readthedocs.io/en/latest/) library.

# Functionality

This bot features an "editor"-like renderer, letting you render custom scenes using sprites from Baba Is You! The `tile` and `rule` commands can be used to render just about anything you want!

![Tile command output](./imgs/tile_command.png?raw=true)
![Rule command output](./imgs/rule_command.png?raw=true)

As hinted at by these demos, there's plenty of nuance in the output -- you can customize to a staggering degree! The following is an example of what you can make:

![Customized gif output](./imgs/fancy_render.gif?raw=true)

In addition to custom renders, the bot also features a `level` command which searches levels by query and renders them. This also supports custom uploaded levels.

![Level command output](./imgs/level_command.png?raw=true)

There are also a number of complementary utility commands, including the `hint` command to provide level hints and the `search` command to search through tiles, levels, color palettes, etc.

A full list of commands can be seen using the `help` command.

![Help command output](./imgs/help_command.png?raw=true)

# Support server

Leave any suggestions, bug reports or questions in the official [support Discord server](https://discord.gg/rMX3YPK).

# To Host This Yourself

Please follow the terms of the license!

Install the requirements: `pip install -r requirements.txt`.

Run the bot using `python3 ROBOT.py`.

(The bot may not work properly on Windows, as it makes use of some unix-ish shell commands for the convenience of the programmer.)

## Required files

Bot configuration is in `config.py`. It contains the following values:

* `activity`: `str` - A "playing" message to set at login.
* `description`: `str` - A description to use in the help command.
* `prefixes`: `list[str]` - A list of strings that can be used to trigger commands.
* `trigger_on_mention`: `bool` - Whether or not bot @mentions will behave as a command prefix.
* `db_path`: `str` - The path to the sqlite3 database used by the bot.
* `embed_color`: `discord.Color` - The color of embedded messages.
* `log_file`: `str` - The file to report logs to.
* `cogs`: `list[str]` - A list of strings -- cogs to load into the bot.
* `original_id`: `int` - If one of your bots can't be invited to servers, put that ID here. Otherwise, set it to 0.

In addition, authentication information should be placed in `auth.py`:

* `tokens`: `list[str]` - A list of bot tokens to use for running this.
* `webhook_url`: `str` - The webhook url used for logging.

If the bot complains about missing files or directories in `cache/` or `target/`, create them.

## Setup commands (bot owner only)

`<>` denotes a required argument, and `[]` denotes an optional argument.

* `loaddata` Collects tile metadata from `values.lua`, `editor_objectlist.lua`, `data/worlds/baba/*.ld` files and `data/custom/*.json` files, and saves it to disk. The following commands are also available, but it is **strongly recommended** to use `loaddata`.
* `loadletters` Scrapes individual letter sprites from image sprites in `data/sprites/*`, as well as pre-made letters from `data/letters/**/*` and places the results in `target/letters/`.
* `loadmap <world_name> <level_id>` Reads and renders an animated GIF of the provided level. `world_name` should be `baba` in most cases. The level metadata is untouched. Useful for re-rendering levels changed in an update without re-doing everything.
* `loadworld <world_name> <should you render mobile levels?>` Reads and renders every single level in `data/levels/<world>/`. Also collects metadata.

* To load tile data, run the `loaddata` command. To load letter data (for custom text), run the `loadletters` command. To load and pre-render levels, run the `loadworld` command.

## Adminstrative commands (bot owner only)

`<>` denotes a required argument, and `[]` denotes an optional argument.

* `load [cog]`(aliases: `reload`, `reloadcog`) Reloads a cog. Useful to hot-reload modules of the bot. If the argument is omitted, all cogs are reloaded.
* `restart` Exits the bot with a return code of 1. (I use this with a process manager that restarts failed tasks.)
* `logout` (aliases: `kill`, `yeet`) Exits the bot with a return code of 0. 
* `ban <user_id>` Adds a user ID to the list of blacklisted users. (This might actually be broken, haven't tested properly)
* `leave <guild_id>` Leaves a guild.
* `hidden` Lists all hidden commands.
* `doc <command>` Displays the docstring for a command.

The bot additionally uses [Jishaku](https://github.com/Gorialis/jishaku/) to interface with `git`, run shell commands and evaluate python. Read more about the `jsk` command at [Jishaku's documentation](https://jishaku.readthedocs.io/en/latest/).

