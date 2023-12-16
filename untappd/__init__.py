from .untappd import Untappd


async def setup(bot):
    await bot.add_cog(Untappd(bot))
