from .traderep import Traderep


def setup(bot):
    bot.add(Traderep())
