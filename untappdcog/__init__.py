"""Import the untappd cog to use for redbot3
It can mostly be ignored"""
from .untappdcog import Untappdcog


def setup(bot):
    """Generic import statement
    This sets up the bot for use"""
    cog = Untappdcog(bot)
    bot.add_cog(cog)
