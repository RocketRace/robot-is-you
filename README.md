# robot-is-you
Discord bot for servers about the indie  game "Baba Is You"

# To Host this Yourself:
Clone this repository. You will need the following additional directories in your working folder:

* setup.json

A json file with the following fields - 
"token": the bot token
"activity" - the message the bot is displayed as Playing
"cogs" - an array of each cog in the format "cogs.cogname"

* palettes/

A directory containing the builtin level palette images

* sprites/

A directory containing the default as well as world-specific sprites you wish to use.

* themes/

A directory containing the builtin theme files ("11theme.txt", etc.). Used to scrape theme-specific objects.

* renders/

An empty directory for image generation.

* log.txt

An empty file for logging. You may disable logging in ROBOT.py.

* levels/

A directory containing the .ld files of each baba level. Used to scrape any additional object data (currently not a feature).
