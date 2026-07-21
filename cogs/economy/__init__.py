from .database import EconomyDB
from .general import EconomyGeneral
from .admin import EconomyAdmin
from .games import EconomyGames
from .economy_help import ECONOMY_COMMAND_DATA  # <-- 1. Import dictionary

async def setup(bot):
    # 1. Fire up your database engine and establish tables first!
    try:
        await EconomyDB.init_db()
        print("📁 Economy Database matrices synchronized successfully!")
    except Exception as e:
        print(f"❌ CRITICAL: Failed to initialize Economy Database: {e}")

    # 2. Register economy command metadata into main COMMAND_DATA dict
    try:
        import main  # Or wherever your central COMMAND_DATA dictionary is located
        if hasattr(main, "COMMAND_DATA"):
            main.COMMAND_DATA.update(ECONOMY_COMMAND_DATA)
            print("📜 Economy commands registered to help menu system.")
    except Exception as e:
        print(f"⚠️ Could not sync economy help metadata: {e}")

    # 3. Load all cog matrices safely
    await bot.add_cog(EconomyGeneral(bot))
    await bot.add_cog(EconomyAdmin(bot))
    await bot.add_cog(EconomyGames(bot))