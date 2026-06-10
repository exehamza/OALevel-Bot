import os
import asyncio
import discord
from discord.ext import commands
from config import Config  # Imports our central configuration setup

# 1. Initialize Bot Intents
intents = discord.Intents.default()
intents.message_content = True  # Required for !commands, !say, !reply, and !snipe
intents.members = True          # Required for on_member_join, logs, kicks, and bans

# --- NEW: SUBCLASSING BOT TO ADD PERSISTENT VIEWS ---
# We create a custom class so we can use `setup_hook`. 
# This ensures buttons keep working after a bot restart.
class ConfessionBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        # We import the Views here to prevent circular import issues
        # (Change 'cogs.confessions' to whatever your confession file path is)
        from cogs.confessions import ConfessionSubmitView, ConfessionApprovalView
        
        # Register the views so they handle button interactions globally
        self.add_view(ConfessionSubmitView())
        self.add_view(ConfessionApprovalView())
        print("Registered persistent confession views successfully!")

# 2. Instantiate the Bot instance (Updated to use our new class)
bot = ConfessionBot(command_prefix=Config.PREFIX, intents=intents)

# 3. Connection Lifecycle Listener
@bot.event
async def on_ready():
    print("==================================================")
    print(f"{bot.user.name} is successfully online and connected!")
    print(f"Prefix configured to: '{Config.PREFIX}'")
    print(f"Connected Guilds: {len(bot.guilds)}")
    print("==================================================")

# 4. Asynchronous Extension/Cog Loader
async def load_extensions():
    if not os.path.exists("./cogs"):
        os.makedirs("./cogs")
        print("'cogs/' directory was missing. Generated empty module folder.")
        return

    print("Initializing extension loaders...")
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            cog_module = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(cog_module)
                print(f"Loaded: {filename[:-3]}")
            except Exception as e:
                print(f"Failed to load extension {filename[:-3]}! Error: {e}")
    print("--------------------------------------------------")

# 5. Core Runtime Entry Point
async def main():
    async with bot:
        await load_extensions()
        
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