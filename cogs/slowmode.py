import discord
from discord.ext import commands
import re

class SlowmodeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # ADD YOUR MODERATOR/STAFF ROLE IDs HERE
        self.ALLOWED_ROLE_IDS = [1256124924356071463]

    def parse_slowmode_duration(self, duration_text):
        """Converts human time strings (e.g., 5s, 2m, 1h) into integers of seconds."""
        duration_text = duration_text.strip().lower()
        
        if duration_text.isdigit():
            return int(duration_text)
            
        match = re.fullmatch(r"(\d+)([smh]?)", duration_text)
        if not match:
            return None

        amount = int(match.group(1))
        unit = match.group(2)

        if unit == "s":
            return amount
        if unit == "m":
            return amount * 60
        if unit == "h":
            return amount * 3600
        return None

    @commands.command(name="slowmode", aliases=["sm"], help="Sets or clears the channel slowmode. Usage: $sm 5s / $sm 0")
    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True) # Bot still needs this to perform the action
    async def slowmode(self, ctx, duration: str = None):
        # Delete the trigger message right away
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        # Custom Role Check: Verify if user has an allowed role or is an Admin/Server Owner
        user_roles = [role.id for role in ctx.author.roles]
        has_bypass_role = any(role_id in self.ALLOWED_ROLE_IDS for role_id in user_roles)
        
        if not has_bypass_role and not ctx.author.guild_permissions.administrator and ctx.author != ctx.guild.owner:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You do not have the required Staff role to use this command.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # If no argument is provided, display current channel status
        if duration is None:
            current_slow = ctx.channel.slowmode_delay
            if current_slow == 0:
                embed = discord.Embed(
                    description="ℹ️ **Slowmode is currently disabled in this channel.**",
                    color=discord.Color.blue()
                )
            else:
                embed = discord.Embed(
                    description=f"ℹ️ **Current slowmode is set to {current_slow} seconds.**",
                    color=discord.Color.blue()
                )
            return await ctx.send(embed=embed)

        # Parse time string to seconds
        seconds = self.parse_slowmode_duration(duration)

        if seconds is None:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Invalid format.** Use format variables like `5s`, `2m`, or `1h`.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if seconds > 21600:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You cannot set a slowmode higher than 6 hours (6h).**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        try:
            await ctx.channel.edit(slowmode_delay=seconds)
            
            if seconds == 0:
                embed = discord.Embed(
                    description="<:Tick:1514986183489360087> **Slowmode has been disabled for this channel.**",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    description=f"<:Tick:1514986183489360087> **Slowmode has been set to {duration} ({seconds} seconds).**",
                    color=discord.Color.green()
                )
            await ctx.send(embed=embed)

        except discord.HTTPException:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Something went wrong while trying to change the slowmode.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @slowmode.error
    async def slowmode_error(self, ctx, error):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        if isinstance(error, commands.BotMissingPermissions):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **I require the Manage Channels permission to alter slowmode parameters.**",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **An unexpected error occurred:**\n`{error}`",
                color=discord.Color.red()
            )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(SlowmodeCog(bot))