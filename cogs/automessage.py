import os
import re
import discord
from discord.ext import commands, tasks

class AutoMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_id = None
        self.interval_seconds = 0
        self.last_message = None
        self.session_name = "May/June 2026"  # Default fallback session
        
        # Custom Emojis
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"

    def cog_unload(self):
        self.automessage_loop.cancel()

    def parse_time(self, time_str: str) -> int:
        """Parses a time string like 1h, 30m, 2d into seconds."""
        time_dict = {"d": 86400, "h": 3600, "m": 60, "s": 1}
        matches = re.findall(r"(\d+)([dhms])", time_str.lower())
        if not matches:
            return 0
        return sum(int(amount) * time_dict[unit] for amount, unit in matches)

    def get_rules_embed(self) -> discord.Embed:
        """Generates the specific rules embed dynamically using the session variable."""
        embed = discord.Embed(
            title="Important Rules Notice",
            description=(
                f"**Do not discuss {self.session_name} content or leaks here!**\n\n"
                "* Discussing papers must only be done in the paper discussion channels.\n"
                "* If the subject channels are locked, you must wait for them to be unlocked before discussing.\n"
                "* Discussion before all variants are over is strictly prohibited.\n"
                "* Any sort of discussion regarding leaks are prohibited."
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text="Not following these rules will result in heavy moderation actions (timeout/ban).")
        return embed

    @tasks.loop(seconds=60)  # Dummy initial interval; changed dynamically
    async def automessage_loop(self):
        if not self.channel_id:
            return

        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return

        # 1. Delete the previous message if it exists
        if self.last_message:
            try:
                await self.last_message.delete()
            except discord.HTTPException:
                pass  # Handles cases where it was already deleted manually

        # 2. Send the new embed message
        try:
            embed = self.get_rules_embed()
            self.last_message = await channel.send(embed=embed)
        except discord.HTTPException as e:
            print(f"Failed to send auto-message: {e}")

    @commands.command(name="automessagesetup", aliases=["amsetup"])
    @commands.has_permissions(manage_messages=True)  # Restrict to staff
    async def automessage_setup(self, ctx, time_interval: str, *, session: str):
        """Sets up the rolling auto-message. Usage: $automessagesetup 1h Oct/Nov 2026"""
        seconds = self.parse_time(time_interval)
        
        if seconds < 10:  # Safety check to prevent rate limits
            embed = discord.Embed(
                description=f"{self.cross} **Please provide a valid time interval greater than 10 seconds** (e.g., `1h`, `30m`).",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        self.channel_id = ctx.channel.id
        self.interval_seconds = seconds
        self.session_name = session  # Assigns your custom session argument to the variable

        # Change the loop interval dynamically and restart it
        self.automessage_loop.change_interval(seconds=self.interval_seconds)
        
        if self.automessage_loop.is_running():
            self.automessage_loop.restart()
        else:
            self.automessage_loop.start()

        embed = discord.Embed(
            description=f"{self.tick} **Auto-message configured for \"{session}\"!** It will repost in this channel every **{time_interval}**.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="automessagestop", aliases=["amstop"])
    @commands.has_permissions(manage_messages=True)
    async def automessage_stop(self, ctx):
        """Stops the active auto-message loop."""
        if self.automessage_loop.is_running():
            self.automessage_loop.cancel()
            self.channel_id = None
            self.last_message = None
            
            embed = discord.Embed(
                description="🛑 **Auto-message loop has been stopped successfully.**",
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                description=f"{self.cross} **There is no active auto-message loop running.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    # Error handling for missing permissions or arguments
    @automessage_setup.error
    async def setup_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                description=f"{self.cross} **Missing arguments.** Correct usage:\n`$automessagesetup [time] [session]`\n*Example: `$automessagesetup 1h Oct/Nov 2026`*",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AutoMessage(bot))