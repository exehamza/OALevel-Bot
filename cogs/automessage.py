import os
import re
import asyncio
import discord
from discord.ext import commands

class AutoMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Dictionary storing active loops per channel ID:
        # { channel_id: { "interval": int, "session": str, "last_message": discord.Message, "task": asyncio.Task } }
        self.active_channels = {}

        # Custom Emojis
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"

    def cog_unload(self):
        """Cancels all active channel tasks when the cog is unloaded/reloaded."""
        for channel_id, data in self.active_channels.items():
            task = data.get("task")
            if task and not task.done():
                task.cancel()

    def parse_time(self, time_str: str) -> int:
        """Parses a time string like 1h, 30m, 2d into seconds."""
        time_dict = {"d": 86400, "h": 3600, "m": 60, "s": 1}
        matches = re.findall(r"(\d+)([dhms])", time_str.lower())
        if not matches:
            return 0
        return sum(int(amount) * time_dict[unit] for amount, unit in matches)

    def get_rules_embed(self, session_name: str) -> discord.Embed:
        """Generates the specific rules embed dynamically using the passed session variable."""
        embed = discord.Embed(
            title="Important Rules Notice",
            description=(
                f"**Do not discuss {session_name} content or leaks here!**\n\n"
                "* Discussing papers must only be done in the paper discussion channels.\n"
                "* If the subject channels are locked, you must wait for them to be unlocked before discussing.\n"
                "* Discussion before all variants are over is strictly prohibited.\n"
                "* Any sort of discussion regarding leaks are prohibited."
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text="Not following these rules will result in heavy moderation actions (timeout/ban).")
        return embed

    async def run_automessage_loop(self, channel_id: int):
        """Independent background loop for a specific channel."""
        try:
            while True:
                data = self.active_channels.get(channel_id)
                if not data:
                    break

                channel = self.bot.get_channel(channel_id)
                if not channel:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except discord.HTTPException:
                        break

                # 1. Delete the previous message if it exists
                if data.get("last_message"):
                    try:
                        await data["last_message"].delete()
                    except discord.HTTPException:
                        pass  # Handled if manually deleted

                # 2. Send the new embed message
                try:
                    embed = self.get_rules_embed(data["session"])
                    data["last_message"] = await channel.send(embed=embed)
                except discord.HTTPException as e:
                    print(f"Failed to send auto-message in channel {channel_id}: {e}")

                # Wait for the channel's specified interval
                await asyncio.sleep(data["interval"])
        except asyncio.CancelledError:
            pass

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

        channel_id = ctx.channel.id

        # Cancel existing task for this channel if one is already running
        if channel_id in self.active_channels:
            old_task = self.active_channels[channel_id].get("task")
            if old_task and not old_task.done():
                old_task.cancel()

        # Initialize tracking structure for this channel
        self.active_channels[channel_id] = {
            "interval": seconds,
            "session": session,
            "last_message": None,
            "task": None
        }

        # Start independent task for this channel
        task = asyncio.create_task(self.run_automessage_loop(channel_id))
        self.active_channels[channel_id]["task"] = task

        embed = discord.Embed(
            description=f"{self.tick} **Auto-message configured for \"{session}\"!** It will repost in this channel every **{time_interval}**.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="automessagestop", aliases=["amstop"])
    @commands.has_permissions(manage_messages=True)
    async def automessage_stop(self, ctx):
        """Stops the active auto-message loop in the current channel."""
        channel_id = ctx.channel.id

        if channel_id in self.active_channels:
            data = self.active_channels.pop(channel_id)
            task = data.get("task")
            if task and not task.done():
                task.cancel()

            embed = discord.Embed(
                description="🛑 **Auto-message loop has been stopped successfully for this channel.**",
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                description=f"{self.cross} **There is no active auto-message loop running in this channel.**",
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
