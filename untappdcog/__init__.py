from .untappdcog import Untappdcog


def setup(bot):
    cog = Untappdcog()
    bot.add_cog(cog(bot))
    cog.create_init_task()
