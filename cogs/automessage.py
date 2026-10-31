import asyncio
import json
import os
import re
import time
import discord
from discord.ext import commands

MANAGEMENT_ROLE_ID = 1272244827693650034

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
    1486373117054943326, 1486373743432437890, 1486374601658335262, 1486372629161050284,
]


def is_management_only():
    """Allows only Management (1272244827693650034), Administrators, or the Server Owner."""
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False
        role_ids = {r.id for r in ctx.author.roles}
        if (
            MANAGEMENT_ROLE_ID in role_ids
            or ctx.author.guild_permissions.administrator
            or ctx.author == ctx.guild.owner
        ):
            return True
        raise commands.MissingPermissions(["administrator"])
    return commands.check(predicate)


class AutoMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.state_file = os.path.join(project_root, "data", "automessage_state.json")
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

        self.state = self._load_state()
        self.master_task: asyncio.Task | None = None
        self._sem = asyncio.Semaphore(10)
        self._lock = asyncio.Lock()
        self._initialized = False

    def cog_unload(self):
        """Cancels the master loop when the cog is reloaded or unloaded."""
        if self.master_task and not self.master_task.done():
            self.master_task.cancel()

    # --- STATE PERSISTENCE ---
    def _load_state(self) -> dict:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return {
                            "active": bool(data.get("active", False)),
                            "interval": int(data.get("interval", 3600)),
                            "time_str": str(data.get("time_str", "1h")),
                            "session": str(data.get("session", "")),
                            "messages": {str(k): int(v) for k, v in data.get("messages", {}).items()},
                        }
            except (json.JSONDecodeError, OSError, ValueError):
                pass
        return {"active": False, "interval": 3600, "time_str": "1h", "session": "", "messages": {}}

    def _save_state(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except OSError as e:
            print(f"[AutoMessage] Failed to save state: {e}")

    # --- HELPERS ---
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

    async def _resolve_channel(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        return channel

    async def _delete_single_message(self, channel_id: int, message_id: int):
        async with self._sem:
            channel = await self._resolve_channel(channel_id)
            if not channel:
                return
            try:
                await channel.get_partial_message(message_id).delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

    async def delete_all_tracked_messages(self):
        """Deletes all stored widget messages concurrently across all channels."""
        tracked = list(self.state.get("messages", {}).items())
        if not tracked:
            return

        await asyncio.gather(
            *(self._delete_single_message(int(ch_id), int(msg_id)) for ch_id, msg_id in tracked),
            return_exceptions=True
        )
        self.state["messages"] = {}
        self._save_state()

    async def _cycle_single_channel(self, channel_id: int, embed: discord.Embed):
        """Deletes the previous widget in a channel (if any) and sends the new one."""
        old_msg_id = self.state["messages"].get(str(channel_id))

        async with self._sem:
            channel = await self._resolve_channel(channel_id)
            if not channel:
                return None

            if old_msg_id:
                try:
                    await channel.get_partial_message(int(old_msg_id)).delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass

            try:
                new_msg = await channel.send(embed=embed)
                return str(channel_id), new_msg.id
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"[AutoMessage] Failed to post in channel {channel_id}: {e}")
                return None

    # --- UNIFIED MASTER LOOP ---
    async def run_master_loop(self):
        """Single synchronized loop that updates all target channels together."""
        try:
            await self.bot.wait_until_ready()
            while self.state.get("active"):
                cycle_start = time.monotonic()

                async with self._lock:
                    if not self.state.get("active"):
                        break

                    embed = self.get_rules_embed(self.state["session"])
                    results = await asyncio.gather(
                        *(self._cycle_single_channel(ch_id, embed) for ch_id in TARGET_CHANNELS),
                        return_exceptions=True
                    )

                    new_messages = {}
                    for res in results:
                        if isinstance(res, tuple) and len(res) == 2:
                            ch_id_str, msg_id = res
                            new_messages[ch_id_str] = msg_id

                    self.state["messages"] = new_messages
                    self._save_state()

                elapsed = time.monotonic() - cycle_start
                sleep_duration = max(1.0, self.state["interval"] - elapsed)
                await asyncio.sleep(sleep_duration)
        except asyncio.CancelledError:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        if self._initialized:
            return
        self._initialized = True

        async with self._lock:
            if self.state.get("messages"):
                print("[AutoMessage] Cleaning up old widget messages from previous session...")
                await self.delete_all_tracked_messages()

        if self.state.get("active") and self.state.get("session"):
            if not self.master_task or self.master_task.done():
                self.master_task = asyncio.create_task(self.run_master_loop())
                print(f"[AutoMessage] Resumed synced loop for '{self.state['session']}'.")

    # --- COMMANDS (MANAGEMENT ONLY) ---
    @commands.command(name="automessagesetup", aliases=["amsetup"])
    @commands.guild_only()
    @is_management_only()
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
            return await ctx.send(embed=embed)

        if self.master_task and not self.master_task.done():
            self.master_task.cancel()
            try:
                await self.master_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            await self.delete_all_tracked_messages()
            self.state["active"] = True
            self.state["interval"] = seconds
            self.state["time_str"] = time_interval
            self.state["session"] = session
            self._save_state()

        self.master_task = asyncio.create_task(self.run_master_loop())

        embed = discord.Embed(
            description=(
                f"{self.tick} **Auto-messages configured for \"{session}\"!**\n"
                f"Now active and synced across **{len(TARGET_CHANNELS)} target channels** reposting every **{time_interval}**."
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="automessagestop", aliases=["amstop"])
    @commands.guild_only()
    @is_management_only()
    async def automessage_stop(self, ctx):
        """Stops auto-messages across all channels and deletes the active widgets."""
        if not self.state.get("active") and not self.state.get("messages"):
            embed = discord.Embed(
                description=f"{self.cross} **There are no active auto-message loops running.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if self.master_task and not self.master_task.done():
            self.master_task.cancel()
            try:
                await self.master_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            self.state["active"] = False
            await self.delete_all_tracked_messages()
            self._save_state()

        embed = discord.Embed(
            description=f"🛑 **Auto-message loops stopped and all active widgets deleted across {len(TARGET_CHANNELS)} target channels.**",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @automessage_setup.error
    @automessage_stop.error
    async def automessage_error(self, ctx, error):
        if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
            embed = discord.Embed(
                description=f"{self.cross} **Only Management members can use this command.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                description=f"{self.cross} **Missing arguments.** Correct usage:\n`$automessagesetup [time] [session]`\n*Example: `$automessagesetup 1h Oct/Nov 2026`*",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AutoMessage(bot))
