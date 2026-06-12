import os
import asyncio
import discord
from discord.ext import commands
from config import Config  # Imports our central configuration setup

# 1. Initialize Bot Intents
intents = discord.Intents.default()
intents.message_content = True  # Required for !commands, !say, !reply, and !snipe
intents.members = True          # Required for on_member_join, logs, kicks, and bans

# --- SUBCLASSING BOT TO ADD PERSISTENT VIEWS ---
class ConfessionBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        # 1. Load extensions FIRST so the modules are fully cooked in memory
        await self.load_extensions()
        
        # 2. Now register persistent views safely
        try:
            from cogs.confessions import ConfessionSubmitView, ConfessionApprovalView
            
            # NOTE: For these to be persistent, the buttons INSIDE these views
            # MUST have a `custom_id` specified!
            self.add_view(ConfessionSubmitView())
            self.add_view(ConfessionApprovalView())
            print("Registered persistent confession views successfully!")
        except Exception as e:
            print(f"Warning: Could not register persistent views: {e}")

    async def load_extensions(self):
        if not os.path.exists("./cogs"):
            os.makedirs("./cogs")
            print("'cogs/' directory was missing. Generated empty module folder.")
            return

        print("Initializing extension loaders...")
        for filename in os.listdir("./cogs"):
            # Ignore hidden files, cache folders, or non-python files
            if filename.endswith(".py") and not filename.startswith("_"):
                cog_module = f"cogs.{filename[:-3]}"
                try:
                    await self.load_extension(cog_module)
                    print(f"Loaded extension: {filename[:-3]}")
                except Exception as e:
                    print(f"Failed to load extension {filename[:-3]}! Error: {e}")
        print("--------------------------------------------------")

# 2. Instantiate the Bot instance
bot = ConfessionBot(command_prefix=Config.PREFIX, intents=intents)

bot.help_command = None

# 3. Connection Lifecycle Listener
@bot.event
async def on_ready():
    print("==================================================")
    print(f"{bot.user.name} is successfully online and connected!")
    print(f"Prefix configured to: '{Config.PREFIX}'")
    print(f"Connected Guilds: {len(bot.guilds)}")
    print("==================================================")

# 4. Core Runtime Entry Point
async def main():
    async with bot:
        if not Config.TOKEN or Config.TOKEN == "your_actual_bot_token_here":
            raise ValueError(
                "CRITICAL ERROR: No valid DISCORD_TOKEN found inside your hidden .env file! "
                "Ensure your token is set up correctly."
            )
            
        await bot.start(Config.TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot interface shutdown sequence initiated. Going offline safely.")