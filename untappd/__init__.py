from .untappd import Untappd


def setup(bot):
    bot.add_cog(Untappd(bot))
