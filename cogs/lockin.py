import discord
from discord.ext import commands
import datetime
import re

class LockIn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def parse_time(self, time_str: str) -> int:
        """
        Parses strings like '10m', '2h', '24h' into total seconds.
        Returns None if the format is invalid.
        """
        # Regular expression to match numbers followed by m (minutes) or h (hours)
        match = re.match(r"^(\d+)([mh])$", time_str.lower().strip())
        if not match:
            return None

        amount = int(match.group(1))
        unit = match.group(2)

        if unit == 'm':
            return amount * 60
        elif unit == 'h':
            return amount * 3600
        return None

    @commands.command(name="lockin")
    @commands.guild_only()  # Prevents users from running this in the bot's DMs
    async def lock_in(self, ctx, time_input: str):
        # 1. Parse the time input
        seconds = self.parse_time(time_input)
        
        if seconds is None:
            return await ctx.send("❌ Invalid format! Please use formats like `10m` (minutes) or `2h` (hours).")

        # 2. Enforce limits (10 minutes minimum, 24 hours maximum)
        MIN_SECONDS = 10 * 60       # 600 seconds
        MAX_SECONDS = 24 * 3600     # 86,400 seconds

        if seconds < MIN_SECONDS:
            return await ctx.send("❌ Minimum lock-in time is `10m` (10 minutes).")
        if seconds > MAX_SECONDS:
            return await ctx.send("❌ Maximum lock-in time is `24h` (24 hours).")

        # 3. Check if the bot has permission to moderate members
        if not ctx.guild.me.guild_permissions.moderate_members:
            return await ctx.send("❌ I don't have the **Moderate Members** (Timeout) permission to lock you in!")

        # 4. Check if the user can actually be timed out (e.g., bot can't timeout Server Owners or higher roles)
        if ctx.author.top_role >= ctx.guild.me.top_role or ctx.author == ctx.guild.owner:
            return await ctx.send("❌ Your power level is too high! I cannot timeout server owners or administrators above me.")

        # 5. Apply the timeout
        # discord.py uses a timedelta added to the current UTC time for timeouts
        duration = datetime.timedelta(seconds=seconds)
        
        try:
            # We use timed_out_until to apply Discord's built-in timeout feature
            await ctx.author.timeout(duration, reason="User initiated !lockin study mode.")
            
            # Send a confirmation message
            embed = discord.Embed(
                title="🔒 Locked In!",
                description=f"{ctx.author.mention} has chosen to lock in for **{time_input}**.\nSee you on the other side! 📚✍️",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            
        except discord.Forbidden:
            await ctx.send("❌ I encountered a permission error trying to mute you.")
        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")

async def setup(bot):
    await bot.add_cog(LockIn(bot))