import os
import re
import asyncio
import discord
from discord.ext import commands

# List of target text channels where auto-messages should post
TARGET_CHANNELS = [
    1539695841948860448, 1256988813771673650, 1392048548996186164, 1392048587516678144,
    1392048640918556692, 1392048775975010326, 1392048706211024978, 1256124924876030066,
    1258677344609243146, 1272297249564786780, 1272297173110882314, 1267578270443114506,
    1327634731977936946, 1399434356400980068, 1256124924876030068, 1293242426189938698,
    1519995459702231101, 1424414233784881315, 1273707840586121216, 1375458675661082654,
    1366061839586299996, 1366000483348512878, 1511346628953505792, 1257922595253125120,
    1487464364268060772, 1256127459984670751, 1256127679011356744, 1256127825925115934,
    1256128035833380904, 1256128236254007447, 1256128708910125107, 1256128494275002439,
    1381340451751067729, 1256129196913328128, 1256128857107599452, 1256129026200703027,
    1257619290044239884, 1256131004637380638, 1256130931186471012, 1256131061155369000,
    1519753414555209859, 1327641228900044810, 1256130815360897046, 1258524579341799424,
    1292531410774786068, 1258524445618999297, 1258524541936734258, 1258524493559890000,
    1258524863056969789, 1258524911568424991, 1258525614042775592, 1367100093450158100,
    1486373117054943326, 1486373743432437890, 1486374601658335262
]

class AutoMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Structure: { channel_id: { "interval": int, "session": str, "last_message": discord.Message, "task": asyncio.Task } }
        self.active_channels = {}

        # Custom Emojis
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"

    def cog_unload(self):
        """Cancels all active background tasks when the cog is reloaded or unloaded."""
        for channel_id, data in list(self.active_channels.items()):
            task = data.get("task")
            if task and not task.done():
                task.cancel()
        self.active_channels.clear()

    def parse_time(self, time_str: str) -> int:
        """Parses a time string like 1h, 30m, 2d into seconds."""
        time_dict = {"d": 86400, "h": 3600, "m": 60, "s": 1}
        matches = re.findall(r"(\d+)([dhms])", time_str.lower())
        if not matches:
            return 0
        return sum(int(amount) * time_dict[unit] for amount, unit in matches)

    def get_rules_embed(self, session_name: str) -> discord.Embed:
        """Generates the rules embed dynamically using the session variable."""
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
        """Independent background loop for a specific target channel."""
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

                # 1. Delete previous auto-message if present
                if data.get("last_message"):
                    try:
                        await data["last_message"].delete()
                    except discord.HTTPException:
                        pass  # Ignored if manually deleted

                # 2. Send updated embed message
                try:
                    embed = self.get_rules_embed(data["session"])
                    data["last_message"] = await channel.send(embed=embed)
                except discord.HTTPException as e:
                    print(f"Failed to post auto-message in channel {channel_id}: {e}")

                # Wait for interval before next repost
                await asyncio.sleep(data["interval"])
        except asyncio.CancelledError:
            pass

    @commands.command(name="automessagesetup", aliases=["amsetup"])
    @commands.has_permissions(manage_messages=True)
    async def automessage_setup(self, ctx, time_interval: str, *, session: str):
        """Sets up the rolling auto-message across ALL specified target channels.
        Usage: $automessagesetup 1h Oct/Nov 2026
        """
        seconds = self.parse_time(time_interval)

        if seconds < 10:
            embed = discord.Embed(
                description=f"{self.cross} **Please provide a valid time interval greater than 10 seconds** (e.g., `1h`, `30m`).",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        # Cancel any active tasks before starting a new setup cycle
        for channel_id, data in list(self.active_channels.items()):
            task = data.get("task")
            if task and not task.done():
                task.cancel()
        self.active_channels.clear()

        # Start background loop for all designated channels
        count = 0
        for channel_id in TARGET_CHANNELS:
            self.active_channels[channel_id] = {
                "interval": seconds,
                "session": session,
                "last_message": None,
                "task": None
            }
            task = asyncio.create_task(self.run_automessage_loop(channel_id))
            self.active_channels[channel_id]["task"] = task
            count += 1

        embed = discord.Embed(
            description=(
                f"{self.tick} **Auto-messages configured for \"{session}\"!**\n"
                f"Now active across **{count} target channels** reposting every **{time_interval}**."
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="automessagestop", aliases=["amstop"])
    @commands.has_permissions(manage_messages=True)
    async def automessage_stop(self, ctx):
        """Stops auto-messages across all channels."""
        if not self.active_channels:
            embed = discord.Embed(
                description=f"{self.cross} **There are no active auto-message loops running.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        count = len(self.active_channels)
        for channel_id, data in list(self.active_channels.items()):
            task = data.get("task")
            if task and not task.done():
                task.cancel()

        self.active_channels.clear()

        embed = discord.Embed(
            description=f"🛑 **Auto-message loops stopped across all {count} target channels.**",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

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
