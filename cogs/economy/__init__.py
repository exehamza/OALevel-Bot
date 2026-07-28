from .database import EconomyDB
from .general import EconomyGeneral
from .admin import EconomyAdmin
from .games import EconomyGames
from .shop import EconomyShop
from .crimes import EconomyCrimes

async def setup(bot):
    # 1. Fire up your database engine and establish tables first!
    try:
        await EconomyDB.init_db()
        print("📁 Economy Database matrices synchronized successfully!")
    except Exception as e:
        print(f"❌ CRITICAL: Failed to initialize Economy Database: {e}")

    # 3. Load all cog matrices safely
    await bot.add_cog(EconomyGeneral(bot))
    await bot.add_cog(EconomyAdmin(bot))
    await bot.add_cog(EconomyGames(bot))
    await bot.add_cog(EconomyShop(bot))
    await bot.add_cog(EconomyCrimes(bot))