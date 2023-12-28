from .traderep import Traderep


async def setup(bot):
    await bot.add_cog(Traderep(bot))
