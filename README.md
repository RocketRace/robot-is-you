# About

A fun Discord bot based on the indie game [Baba Is You](https://store.steampowered.com/app/736260/Baba_Is_You/) (by Arvi Teikkari). This bot was written with the [discord.py](https://discordpy.readthedocs.io/en/latest/) library for Python 3.x.

# Functionality

A list of all commands can be seen using the `help` command. (By default, the bot has a prefix of `+`.)

This bot primarily features rendering and animation of tiles in *Baba Is You*, through the `tile` and `rule` commands, as seen below. The command has many options, detailed in `help tile`.

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

Support is not provided for self-hosting. You may run the code yourself given that you follow the terms of the license.

~

The bot uses the discord.py >= 1.0.0 and Pillow >= 6.1.0 modules from pip.

The bot requires a `setup.json` file to boot up. This includes the following fields:

* `token`: str

* `prefixes`: List\<str\>

* `activity`: str

* `cogs`: List\<str\> [Each file in the cogs folder, in python import format]

* `webhook`: int [A webhook ID used for error logging]

* `embed-color`: int

~

The bot scrapes tile information from Baba Is You level files (`.ld` extension), from a top-level folder `levels`.

Tile colors are gathered from the in-game palette images, from a top-level folder `palettes`.

Tile sprites are taken from `sprites/[source]/`, where `source` is `vanilla` for regular tiles and otherwise specified for custom tiles. Sprites should be in the same format that they are stored in Baba Is You.

`empty.png`, a fully transparent 24x24 image is used for blank tiles.

~

*[Files/directories empty by default]*

Renders are stored in `renders/`. Currently, only the most recent are stored (by overwriting).

A list of tiles (for `+list`) is stored in `tilelist.txt`.

Tile data is stored in `tiledata.json`.

Scraped data is stored in `alternatetiles.json`.

~
