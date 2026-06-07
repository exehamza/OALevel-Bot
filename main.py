import os
import asyncio
import discord
from discord.ext import commands
from config import Config  # Imports our central configuration setup

# 1. Initialize Bot Intents
# Intents act as permissions telling Discord what events your bot should receive.
intents = discord.Intents.default()
intents.message_content = True  # Required for !commands, !say, !reply, and !snipe
intents.members = True          # Required for on_member_join, logs, kicks, and bans

# 2. Instantiate the Bot instance
bot = commands.Bot(command_prefix=Config.PREFIX, intents=intents)

# 3. Connection Lifecyle Listener
@bot.event
async def on_ready():
    print("==================================================")
    print(f"{bot.user.name} is successfully online and connected!")
    print(f"Prefix configured to: '{Config.PREFIX}'")
    print(f"Connected Guilds: {len(bot.guilds)}")
    print("==================================================")

# 4. Asynchronous Extension/Cog Loader
async def load_extensions():
    # Defensive check: automatically verify if the cogs directory exists
    if not os.path.exists("./cogs"):
        os.makedirs("./cogs")
        print("'cogs/' directory was missing. Generated empty module folder.")
        return

    print("Initializing extension loaders...")
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            # Strip the '.py' file extension to import as a dot-notation module path
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
        # Load your cogs before invoking connection methods
        await load_extensions()
        
        # Guard clause: make sure the token isn't blank or missing from your environment variables
        if not Config.TOKEN or Config.TOKEN == "your_actual_bot_token_here":
            raise ValueError(
                "CRITICAL ERROR: No valid DISCORD_TOKEN found inside your hidden .env file! "
                "Ensure your token is set up correctly."
            )
            
        # Start connection sequence
        await bot.start(Config.TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot interface shutdown sequence initiated. Going offline safely.")