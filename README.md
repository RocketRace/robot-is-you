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

Support is not provided for self-hosting. You may run the code yourself given that you follow the terms of the license.

---

Install the requirements: `pip install -r requirements.txt`.

Bot configuration is in `config/setup.json`. The `auth_file` field should point to a JSON file with a `token` field with your bot token. Other fields are documented through their existence.

Run the bot using `python3 ROBOT.py`.

If the bot complains about missing files in `cache/`, create them.

The bot may or may not work properly on Windows, or MacOS.
