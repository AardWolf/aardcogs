# How to Contribute

Thank you for your interest! This project was started as a first python project by a beer enthusiast. If you have python experience, be gentle and know that "better ways to do it" are welcome! If you're new to python, welcome!

We can usually be found over on [Discord](https://discord.me/Untappd) in the Untappd server, discussing beer. Bot/cog suggestions go in #suggestion_box but we also watch the "entry" channel if you don't want to go through the steps to be able to chat on that server.

In general - grab a branch (main is a good one), make your changes, and submit a pull request with good notes about what's up. They'll get reviewed and added/changed/etc.

# Useful Resources

These cogs work with [Red](https://red-discordbot.readthedocs.io/en/v3-develop/) (we're upgrading to v3 Real Soon Now). This includes [discord.py](https://discordpy.readthedocs.io/en/v1.0.1/index.html).

If you want to set up a test environment for yourself, go create a Discord server. Then create a new [Discord App](https://discordapp.com/developers/applications/) for your test bot. You'll be able to invite your bot to this server.

When testing it's been easy to make local changes to files, copy them into your bot's cogs directory, and telling the bot to reload that cog. If you then with to confirm it can pull the thing from Github you can commit it to your repo and set up your test bot to use that repo and overwrite the cog file.


