import asyncio
import io
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import discord
from discord.ext import commands, tasks
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "database.sqlite")
BLACKLIST_JSON_PATH = os.path.join(BASE_DIR, "data", "serverstats_blacklist.json")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

STATBOT_GREEN = 0x43B581
STATBOT_BLUE = 0x3880D4

# Default blacklisted staff & miscellaneous channel IDs
DEFAULT_BLACKLISTED_CHANNELS = {
    1296530025637740554,
    1259939909695832085,
    1479417611551903855,
    1379144193942884484,
    1371762494640619530,
    1370123522784886784,
    1325095384342597692,
    1324373003680743503,
    1256143953112072193,
    1336666840134324246,
    1543301161006932089,
    1368512766435921920,
    1256124924381364237,
    1256752277230977104,
    1256124924876030064,
    1272313232412901488,
    1375458195891294298,
    1337514542501990431,
    1272319224077094992,
    1272324041834758258,
    1269375026101223535,
    1270860358923325580,
    1309217890200719421,
    1355141599067373781,
    1256124925723541526,
    1256124925723541530,
}


def today_bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def date_buckets(days: int) -> list[str]:
    now = datetime.now(timezone.utc)
    return [
        (now - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(days - 1, -1, -1)
    ]


def parse_days_arg(arg: Optional[str], default: int = 14) -> Optional[int]:
    if not arg:
        return None
    cleaned = arg.strip().lower()
    match = re.fullmatch(r"(\d{1,3})d?", cleaned)
    if not match:
        return None
    val = int(match.group(1))
    return max(1, min(val, 90))


def format_voice_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds == 0:
        return "0m"
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours:,}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m"
    return f"{secs}s"


def format_voice_hours(seconds: int) -> str:
    return f"{seconds / 3600:.2f} hrs"


class ServerStats(commands.Cog):
    """Statbot-style Server Statistics: $channel, $chart, $me, $server, $stats, $top, $user."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = DB_PATH
        self.blacklist_path = BLACKLIST_JSON_PATH
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"

        self.blacklisted_channels: set[int] = self._load_blacklisted_channels()

        # Active voice sessions: {(guild_id, user_id): (channel_id, start_monotonic)}
        self._voice_sessions: dict[Tuple[int, int], Tuple[int, float]] = {}

        self._init_db()
        self.voice_flush_loop.start()

    def cog_unload(self):
        self.voice_flush_loop.cancel()
        self._flush_all_voice_sessions()

    # ------------------------------------------------------------------
    # Blacklist JSON Persistence & Channel Checks
    # ------------------------------------------------------------------

    def _load_blacklisted_channels(self) -> set[int]:
        channels = set(DEFAULT_BLACKLISTED_CHANNELS)
        if os.path.exists(self.blacklist_path):
            try:
                with open(self.blacklist_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        loaded = data.get("blacklisted_channels", [])
                    elif isinstance(data, list):
                        loaded = data
                    else:
                        loaded = []
                    for cid in loaded:
                        if str(cid).isdigit():
                            channels.add(int(cid))
            except (json.JSONDecodeError, OSError):
                pass

        self._save_blacklisted_channels(channels)
        return channels

    def _save_blacklisted_channels(self, channels: set[int]):
        try:
            with open(self.blacklist_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"blacklisted_channels": sorted(channels)},
                    f,
                    indent=2,
                )
                f.write("\n")
        except OSError as e:
            print(f"[ServerStats] Failed to save blacklist JSON: {e}")

    def _is_channel_blacklisted(self, channel) -> bool:
        """Checks if a channel, its parent thread channel, or its category is blacklisted."""
        if channel is None:
            return True
        cid = getattr(channel, "id", None)
        parent_id = getattr(channel, "parent_id", None)
        category_id = getattr(channel, "category_id", None)
        return (
            cid in self.blacklisted_channels
            or parent_id in self.blacklisted_channels
            or category_id in self.blacklisted_channels
        )

    # ------------------------------------------------------------------
    # Database Initialization & Helpers
    # ------------------------------------------------------------------

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stat_messages (
                    guild_id INTEGER,
                    user_id INTEGER,
                    channel_id INTEGER,
                    day TEXT,
                    count INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id, channel_id, day)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stat_voice (
                    guild_id INTEGER,
                    user_id INTEGER,
                    channel_id INTEGER,
                    day TEXT,
                    seconds INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id, channel_id, day)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stat_member_flow (
                    guild_id INTEGER,
                    day TEXT,
                    joins INTEGER DEFAULT 0,
                    leaves INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, day)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stat_msg_guild_day ON stat_messages (guild_id, day)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stat_vc_guild_day ON stat_voice (guild_id, day)")

            # Purge any historical rows belonging to blacklisted channels
            if self.blacklisted_channels:
                placeholders = ",".join("?" for _ in self.blacklisted_channels)
                bl_tuple = tuple(self.blacklisted_channels)
                cursor.execute(f"DELETE FROM stat_messages WHERE channel_id IN ({placeholders})", bl_tuple)
                cursor.execute(f"DELETE FROM stat_voice WHERE channel_id IN ({placeholders})", bl_tuple)

            conn.commit()

    def _record_message(self, guild_id: int, user_id: int, channel_id: int):
        if channel_id in self.blacklisted_channels:
            return
        day = today_bucket()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO stat_messages (guild_id, user_id, channel_id, day, count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(guild_id, user_id, channel_id, day)
                DO UPDATE SET count = count + 1
            """, (guild_id, user_id, channel_id, day))
            conn.commit()

    def _record_voice_seconds(self, guild_id: int, user_id: int, channel_id: int, seconds: int):
        if seconds <= 0 or channel_id in self.blacklisted_channels:
            return
        day = today_bucket()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO stat_voice (guild_id, user_id, channel_id, day, seconds)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id, channel_id, day)
                DO UPDATE SET seconds = seconds + excluded.seconds
            """, (guild_id, user_id, channel_id, day, seconds))
            conn.commit()

    def _record_member_flow(self, guild_id: int, *, joined: bool):
        day = today_bucket()
        col = "joins" if joined else "leaves"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"""
                INSERT INTO stat_member_flow (guild_id, day, {col})
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id, day)
                DO UPDATE SET {col} = {col} + 1
            """, (guild_id, day))
            conn.commit()

    def _flush_all_voice_sessions(self):
        now = time.monotonic()
        for (guild_id, user_id), (channel_id, started) in list(self._voice_sessions.items()):
            if channel_id in self.blacklisted_channels:
                self._voice_sessions.pop((guild_id, user_id), None)
                continue
            elapsed = int(now - started)
            if elapsed > 0:
                self._record_voice_seconds(guild_id, user_id, channel_id, elapsed)
                self._voice_sessions[(guild_id, user_id)] = (channel_id, now)

    @tasks.loop(minutes=2)
    async def voice_flush_loop(self):
        await asyncio.to_thread(self._flush_all_voice_sessions)

    @voice_flush_loop.before_loop
    async def before_voice_flush_loop(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Event Listeners
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self):
        now = time.monotonic()
        for guild in self.bot.guilds:
            for vc in guild.voice_channels + guild.stage_channels:
                if self._is_channel_blacklisted(vc):
                    continue
                for member in vc.members:
                    if not member.bot and not (member.voice and (member.voice.self_deaf or member.voice.deaf)):
                        self._voice_sessions.setdefault((guild.id, member.id), (vc.id, now))
        print(f"ServerStats initialized ({len(self.blacklisted_channels)} channels blacklisted).")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if self._is_channel_blacklisted(message.channel):
            return
        channel_id = getattr(message.channel, "parent_id", None) or message.channel.id
        if channel_id in self.blacklisted_channels:
            return
        await asyncio.to_thread(self._record_message, message.guild.id, message.author.id, channel_id)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        key = (member.guild.id, member.id)
        now = time.monotonic()

        # Flush any previous session first
        if key in self._voice_sessions:
            old_channel_id, started = self._voice_sessions.pop(key)
            elapsed = int(now - started)
            if elapsed > 0 and old_channel_id not in self.blacklisted_channels:
                await asyncio.to_thread(self._record_voice_seconds, member.guild.id, member.id, old_channel_id, elapsed)

        # Start a new session if user is in a non-blacklisted voice channel and not deafened
        if (
            after.channel is not None
            and not self._is_channel_blacklisted(after.channel)
            and not (after.self_deaf or after.deaf)
        ):
            self._voice_sessions[key] = (after.channel.id, now)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            await asyncio.to_thread(self._record_member_flow, member.guild.id, joined=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member.bot:
            await asyncio.to_thread(self._record_member_flow, member.guild.id, joined=False)

    # ------------------------------------------------------------------
    # Chart Renderer (Statbot Dark Theme)
    # ------------------------------------------------------------------

    def _render_statbot_chart(
        self,
        days_list: list[str],
        values: list[float],
        title: str,
        ylabel: str,
        color: str = "#43b581",
        secondary_values: Optional[list[float]] = None,
        primary_label: Optional[str] = None,
        secondary_label: Optional[str] = None,
    ) -> io.BytesIO:
        dates = [datetime.strptime(d, "%Y-%m-%d") for d in days_list]

        fig, ax = plt.subplots(figsize=(8.5, 3.6), dpi=140)
        fig.patch.set_facecolor("#2b2d31")
        ax.set_facecolor("#1e1f22")

        ax.plot(dates, values, color=color, linewidth=2.4, marker="o", markersize=4, label=primary_label)
        ax.fill_between(dates, values, color=color, alpha=0.22)

        if secondary_values is not None:
            ax.plot(
                dates,
                secondary_values,
                color="#ed4245",
                linewidth=2.2,
                marker="o",
                markersize=4,
                label=secondary_label,
            )
            ax.fill_between(dates, secondary_values, color="#ed4245", alpha=0.18)
            ax.legend(facecolor="#2b2d31", edgecolor="#3f4147", labelcolor="white", fontsize=9)

        ax.set_title(title, color="#ffffff", fontsize=12, fontweight="bold", pad=12)
        ax.set_ylabel(ylabel, color="#b5bac1", fontsize=10)

        ax.grid(True, linestyle="--", linewidth=0.6, color="#3f4147", alpha=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#3f4147")
        ax.spines["bottom"].set_color("#3f4147")

        ax.tick_params(axis="x", colors="#b5bac1", labelsize=8.5)
        ax.tick_params(axis="y", colors="#b5bac1", labelsize=8.5)
        ax.set_ylim(bottom=0)

        interval = max(1, len(dates) // 7)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=interval))

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", facecolor=fig.get_facecolor(), edgecolor="none")
        buf.seek(0)
        plt.close(fig)
        return buf

    # ------------------------------------------------------------------
    # Query Helpers
    # ------------------------------------------------------------------

    def _window_cutoff(self, days: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    def _get_user_rank_and_windows(self, guild: discord.Guild, user_id: int) -> dict:
        self._flush_all_voice_sessions()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()

            msg_windows = {}
            vc_windows = {}
            for d in (1, 7, 14, 30):
                cutoff = self._window_cutoff(d)
                cur.execute(
                    "SELECT COALESCE(SUM(count), 0) FROM stat_messages WHERE guild_id = ? AND user_id = ? AND day >= ?",
                    (guild.id, user_id, cutoff),
                )
                msg_windows[d] = cur.fetchone()[0]

                cur.execute(
                    "SELECT COALESCE(SUM(seconds), 0) FROM stat_voice WHERE guild_id = ? AND user_id = ? AND day >= ?",
                    (guild.id, user_id, cutoff),
                )
                vc_windows[d] = cur.fetchone()[0]

            cutoff_14 = self._window_cutoff(14)

            # Compute active-member message rank (14d)
            cur.execute(
                "SELECT user_id, SUM(count) as total FROM stat_messages WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY total DESC",
                (guild.id, cutoff_14),
            )
            msg_rank = None
            rank_counter = 1
            for uid, _ in cur.fetchall():
                m = guild.get_member(uid)
                if m is not None and not m.bot:
                    if uid == user_id:
                        msg_rank = rank_counter
                        break
                    rank_counter += 1

            # Compute active-member voice rank (14d)
            cur.execute(
                "SELECT user_id, SUM(seconds) as total FROM stat_voice WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY total DESC",
                (guild.id, cutoff_14),
            )
            vc_rank = None
            rank_counter = 1
            for uid, _ in cur.fetchall():
                m = guild.get_member(uid)
                if m is not None and not m.bot:
                    if uid == user_id:
                        vc_rank = rank_counter
                        break
                    rank_counter += 1

            # Top non-blacklisted channels for this user (14d)
            cur.execute(
                "SELECT channel_id, SUM(count) as total FROM stat_messages WHERE guild_id = ? AND user_id = ? AND day >= ? GROUP BY channel_id ORDER BY total DESC",
                (guild.id, user_id, cutoff_14),
            )
            top_channels = []
            for cid, cnt in cur.fetchall():
                ch_obj = guild.get_channel(cid)
                if ch_obj is not None and not self._is_channel_blacklisted(ch_obj):
                    top_channels.append((cid, cnt))
                    if len(top_channels) == 5:
                        break

        return {
            "msg_windows": msg_windows,
            "vc_windows": vc_windows,
            "msg_rank": msg_rank,
            "vc_rank": vc_rank,
            "top_channels": top_channels,
        }

    def _get_daily_series(
        self,
        guild_id: int,
        days: int,
        *,
        table: str = "stat_messages",
        col: str = "count",
        user_id: Optional[int] = None,
        channel_id: Optional[int] = None,
    ) -> tuple[list[str], list[int]]:
        self._flush_all_voice_sessions()
        buckets = date_buckets(days)
        cutoff = buckets[0]

        query = f"SELECT day, COALESCE(SUM({col}), 0) FROM {table} WHERE guild_id = ? AND day >= ?"
        params: list = [guild_id, cutoff]
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        if channel_id is not None:
            query += " AND channel_id = ?"
            params.append(channel_id)
        query += " GROUP BY day"

        with sqlite3.connect(self.db_path) as conn:
            rows = dict(conn.execute(query, params).fetchall())

        return buckets, [int(rows.get(d, 0)) for d in buckets]

    # ------------------------------------------------------------------
    # 1. $channel — See a channel's stats.
    # ------------------------------------------------------------------

    @commands.command(name="channel", help="See a channel's stats.")
    @commands.guild_only()
    async def channel_stats(
        self,
        ctx: commands.Context,
        target_or_days: Optional[str] = None,
        days_arg: Optional[str] = None,
    ):
        """See a channel's stats. Usage: $channel [#channel] [days]"""
        if not ctx.guild.chunked:
            await ctx.guild.chunk()

        channel = ctx.channel
        days = 14

        if target_or_days:
            parsed_d = parse_days_arg(target_or_days)
            if parsed_d is not None:
                days = parsed_d
            else:
                try:
                    channel = await commands.GuildChannelConverter().convert(ctx, target_or_days)
                except commands.BadArgument:
                    embed = discord.Embed(
                        description=f"{self.cross} **Could not find that channel.** Usage: `$channel [#channel] [days]`",
                        color=discord.Color.red(),
                    )
                    return await ctx.send(embed=embed)

        if days_arg:
            parsed_d2 = parse_days_arg(days_arg)
            if parsed_d2 is not None:
                days = parsed_d2

        if self._is_channel_blacklisted(channel):
            embed = discord.Embed(
                description=f"{self.cross} **This channel is excluded from Server Statistics.**",
                color=discord.Color.red(),
            )
            return await ctx.send(embed=embed)

        is_voice = isinstance(channel, (discord.VoiceChannel, discord.StageChannel))
        self._flush_all_voice_sessions()

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            table = "stat_voice" if is_voice else "stat_messages"
            col = "seconds" if is_voice else "count"

            windows = {}
            for d in (1, 7, 14, 30):
                cutoff = self._window_cutoff(d)
                cur.execute(
                    f"SELECT COALESCE(SUM({col}), 0) FROM {table} WHERE guild_id = ? AND channel_id = ? AND day >= ?",
                    (ctx.guild.id, channel.id, cutoff),
                )
                windows[d] = cur.fetchone()[0]

            cutoff_custom = self._window_cutoff(days)

            # Channel Rank across non-blacklisted server channels
            cur.execute(
                f"SELECT channel_id, SUM({col}) as total FROM {table} WHERE guild_id = ? AND day >= ? GROUP BY channel_id ORDER BY total DESC",
                (ctx.guild.id, cutoff_custom),
            )
            ch_rank = None
            r_idx = 1
            for cid, _ in cur.fetchall():
                ch_obj = ctx.guild.get_channel(cid)
                if ch_obj is not None and not self._is_channel_blacklisted(ch_obj):
                    if cid == channel.id:
                        ch_rank = r_idx
                        break
                    r_idx += 1

            # Unique active contributors & top 5 members in this channel
            cur.execute(
                f"SELECT user_id, SUM({col}) as total FROM {table} WHERE guild_id = ? AND channel_id = ? AND day >= ? GROUP BY user_id ORDER BY total DESC",
                (ctx.guild.id, channel.id, cutoff_custom),
            )
            all_contributors = cur.fetchall()

        active_contributors = []
        for uid, val in all_contributors:
            member = ctx.guild.get_member(uid)
            if member is not None and not member.bot:
                active_contributors.append((member, val))

        top_members = active_contributors[:5]

        buckets, series = self._get_daily_series(
            ctx.guild.id,
            days,
            table=table,
            col=col,
            channel_id=channel.id,
        )

        if is_voice:
            plot_vals = [round(v / 3600, 2) for v in series]
            ylabel = "Hours"
            unit_fmt = format_voice_duration
        else:
            plot_vals = series
            ylabel = "Messages"
            unit_fmt = lambda v: f"{v:,} msgs"

        chart_buf = await asyncio.to_thread(
            self._render_statbot_chart,
            buckets,
            plot_vals,
            f"#{channel.name} — Last {days} Days",
            ylabel,
        )

        embed = discord.Embed(
            title=f"📊 Channel Stats — #{channel.name}",
            description=f"Activity overview for {channel.mention} (`Last {days} Days`)",
            color=STATBOT_GREEN,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="⏱️ Timeframe Totals",
            value=(
                f"• **1d:** `{unit_fmt(windows[1])}`\n"
                f"• **7d:** `{unit_fmt(windows[7])}`\n"
                f"• **14d:** `{unit_fmt(windows[14])}`\n"
                f"• **30d:** `{unit_fmt(windows[30])}`"
            ),
            inline=True,
        )
        embed.add_field(
            name="🏆 Channel Standing",
            value=(
                f"• **Server Rank ({days}d):** `{f'#{ch_rank}' if ch_rank else 'Unranked'}`\n"
                f"• **Contributors ({days}d):** `{len(active_contributors):,}`\n"
                f"• **Type:** `{'Voice' if is_voice else 'Text'}`"
            ),
            inline=True,
        )

        if top_members:
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            top_lines = [
                f"{medals.get(idx, f'`#{idx}`')} {m.mention} — `{unit_fmt(val)}`"
                for idx, (m, val) in enumerate(top_members, start=1)
            ]
            embed.add_field(
                name=f"👥 Top Members ({days}d)",
                value="\n".join(top_lines),
                inline=False,
            )
        else:
            embed.add_field(
                name=f"👥 Top Members ({days}d)",
                value="*No activity recorded in this timeframe yet.*",
                inline=False,
            )

        file = discord.File(chart_buf, filename="channel_chart.png")
        embed.set_image(url="attachment://channel_chart.png")
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed, file=file)

    # ------------------------------------------------------------------
    # 2. $chart — Generate a detailed chart.
    # ------------------------------------------------------------------

    @commands.command(name="chart", help="Generate a detailed chart.")
    @commands.guild_only()
    async def chart_command(
        self,
        ctx: commands.Context,
        arg1: Optional[str] = None,
        arg2: Optional[str] = None,
        arg3: Optional[str] = None,
    ):
        """Generate a detailed chart. Usage: $chart [messages|voice|members|#channel|@user] [days]"""
        days = 14
        chart_type = "messages"
        target_member: Optional[discord.Member] = None
        target_channel: Optional[discord.abc.GuildChannel] = None

        tokens = [t for t in (arg1, arg2, arg3) if t is not None]
        for token in tokens:
            low = token.lower().strip()
            parsed_d = parse_days_arg(low)
            if parsed_d is not None:
                days = parsed_d
                continue
            if low in ("messages", "message", "msg", "msgs"):
                chart_type = "messages"
                continue
            if low in ("voice", "vc", "audio"):
                chart_type = "voice"
                continue
            if low in ("members", "member", "joins", "growth"):
                chart_type = "members"
                continue
            if low in ("channel", "user"):
                continue

            try:
                target_channel = await commands.GuildChannelConverter().convert(ctx, token)
                chart_type = "channel"
                continue
            except commands.BadArgument:
                pass

            try:
                target_member = await commands.MemberConverter().convert(ctx, token)
                chart_type = "user"
                continue
            except commands.BadArgument:
                pass

        buckets = date_buckets(days)

        if chart_type == "members":
            cutoff = buckets[0]
            with sqlite3.connect(self.db_path) as conn:
                rows = {
                    day: (j, l)
                    for day, j, l in conn.execute(
                        "SELECT day, joins, leaves FROM stat_member_flow WHERE guild_id = ? AND day >= ?",
                        (ctx.guild.id, cutoff),
                    ).fetchall()
                }
            joins_series = [rows.get(d, (0, 0))[0] for d in buckets]
            leaves_series = [rows.get(d, (0, 0))[1] for d in buckets]

            chart_buf = await asyncio.to_thread(
                self._render_statbot_chart,
                buckets,
                joins_series,
                f"{ctx.guild.name} — Member Flow (Last {days} Days)",
                "Members",
                "#43b581",
                leaves_series,
                "Joins",
                "Leaves",
            )
            embed = discord.Embed(
                title=f"📈 Member Flow Chart ({days}d)",
                description=(
                    f"• **Total Joins:** `+{sum(joins_series):,}`\n"
                    f"• **Total Leaves:** `-{sum(leaves_series):,}`\n"
                    f"• **Net Change:** `{sum(joins_series) - sum(leaves_series):+,}`"
                ),
                color=STATBOT_GREEN,
                timestamp=discord.utils.utcnow(),
            )

        elif chart_type == "voice":
            buckets, series = self._get_daily_series(ctx.guild.id, days, table="stat_voice", col="seconds")
            hours_series = [round(s / 3600, 2) for s in series]
            chart_buf = await asyncio.to_thread(
                self._render_statbot_chart,
                buckets,
                hours_series,
                f"{ctx.guild.name} — Voice Activity (Last {days} Days)",
                "Voice Hours",
                "#3880d4",
            )
            embed = discord.Embed(
                title=f"🎙️ Server Voice Chart ({days}d)",
                description=f"• **Total Voice Time:** `{format_voice_duration(sum(series))}` (`{format_voice_hours(sum(series))}`)",
                color=STATBOT_BLUE,
                timestamp=discord.utils.utcnow(),
            )

        elif chart_type == "channel" and target_channel is not None:
            if self._is_channel_blacklisted(target_channel):
                embed = discord.Embed(
                    description=f"{self.cross} **That channel is excluded from Server Statistics.**",
                    color=discord.Color.red(),
                )
                return await ctx.send(embed=embed)

            is_vc = isinstance(target_channel, (discord.VoiceChannel, discord.StageChannel))
            table = "stat_voice" if is_vc else "stat_messages"
            col = "seconds" if is_vc else "count"
            buckets, series = self._get_daily_series(
                ctx.guild.id, days, table=table, col=col, channel_id=target_channel.id
            )
            plot_vals = [round(s / 3600, 2) for s in series] if is_vc else series
            ylabel = "Voice Hours" if is_vc else "Messages"
            chart_buf = await asyncio.to_thread(
                self._render_statbot_chart,
                buckets,
                plot_vals,
                f"#{target_channel.name} — Last {days} Days",
                ylabel,
            )
            total_str = format_voice_duration(sum(series)) if is_vc else f"{sum(series):,} messages"
            embed = discord.Embed(
                title=f"📈 Channel Chart — #{target_channel.name} ({days}d)",
                description=f"• **Channel:** {target_channel.mention}\n• **Total ({days}d):** `{total_str}`",
                color=STATBOT_GREEN,
                timestamp=discord.utils.utcnow(),
            )

        elif chart_type == "user" and target_member is not None:
            buckets, series = self._get_daily_series(
                ctx.guild.id, days, table="stat_messages", col="count", user_id=target_member.id
            )
            chart_buf = await asyncio.to_thread(
                self._render_statbot_chart,
                buckets,
                series,
                f"@{target_member.name} — Messages (Last {days} Days)",
                "Messages",
            )
            embed = discord.Embed(
                title=f"📈 User Activity Chart — {target_member.display_name} ({days}d)",
                description=f"• **Member:** {target_member.mention}\n• **Total Messages ({days}d):** `{sum(series):,}`",
                color=STATBOT_GREEN,
                timestamp=discord.utils.utcnow(),
            )

        else:
            buckets, series = self._get_daily_series(ctx.guild.id, days, table="stat_messages", col="count")
            chart_buf = await asyncio.to_thread(
                self._render_statbot_chart,
                buckets,
                series,
                f"{ctx.guild.name} — Messages (Last {days} Days)",
                "Messages",
            )
            embed = discord.Embed(
                title=f"📈 Server Message Chart ({days}d)",
                description=(
                    f"• **Total Messages ({days}d):** `{sum(series):,}`\n"
                    f"• **Daily Average:** `{sum(series) / max(1, days):,.1f} msgs/day`"
                ),
                color=STATBOT_GREEN,
                timestamp=discord.utils.utcnow(),
            )

        file = discord.File(chart_buf, filename="stat_chart.png")
        embed.set_image(url="attachment://stat_chart.png")
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed, file=file)

    # ------------------------------------------------------------------
    # 3 & 7. $user & $me — See a user's / your stats in this server.
    # ------------------------------------------------------------------

    async def _send_user_stats(self, ctx: commands.Context, member: discord.Member, days: int):
        if member.bot:
            embed = discord.Embed(
                description=f"{self.cross} **Bots are excluded from server statistics.**",
                color=discord.Color.red(),
            )
            return await ctx.send(embed=embed)

        if not ctx.guild.chunked:
            await ctx.guild.chunk()

        data = await asyncio.to_thread(self._get_user_rank_and_windows, ctx.guild, member.id)
        buckets, msg_series = self._get_daily_series(
            ctx.guild.id, days, table="stat_messages", col="count", user_id=member.id
        )

        chart_buf = await asyncio.to_thread(
            self._render_statbot_chart,
            buckets,
            msg_series,
            f"@{member.name} — Message Activity (Last {days} Days)",
            "Messages",
        )

        mw = data["msg_windows"]
        vw = data["vc_windows"]
        m_rank = f"#{data['msg_rank']}" if data["msg_rank"] else "Unranked"
        v_rank = f"#{data['vc_rank']}" if data["vc_rank"] else "Unranked"

        embed = discord.Embed(
            title=f"📊 Member Statistics — {member.display_name}",
            description=f"Server activity overview for {member.mention}",
            color=STATBOT_GREEN,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(
            name=f"💬 Messages (14d Rank: {m_rank})",
            value=(
                f"• **1d:** `{mw[1]:,}`\n"
                f"• **7d:** `{mw[7]:,}`\n"
                f"• **14d:** `{mw[14]:,}`\n"
                f"• **30d:** `{mw[30]:,}`"
            ),
            inline=True,
        )
        embed.add_field(
            name=f"🎙️ Voice Time (14d Rank: {v_rank})",
            value=(
                f"• **1d:** `{format_voice_duration(vw[1])}`\n"
                f"• **7d:** `{format_voice_duration(vw[7])}`\n"
                f"• **14d:** `{format_voice_duration(vw[14])}`\n"
                f"• **30d:** `{format_voice_duration(vw[30])}`"
            ),
            inline=True,
        )

        top_ch = data["top_channels"]
        if top_ch:
            ch_lines = []
            for idx, (cid, cnt) in enumerate(top_ch, start=1):
                ch_lines.append(f"`#{idx}` <#{cid}> — `{cnt:,}` msgs")
            embed.add_field(
                name="📌 Most Active Channels (14d)",
                value="\n".join(ch_lines),
                inline=False,
            )
        else:
            embed.add_field(
                name="📌 Most Active Channels (14d)",
                value="*No recent channel activity recorded.*",
                inline=False,
            )

        file = discord.File(chart_buf, filename="user_stats.png")
        embed.set_image(url="attachment://user_stats.png")
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed, file=file)

    @commands.command(name="me", help="See your stats in this server.")
    @commands.guild_only()
    async def me_stats(self, ctx: commands.Context, days_arg: Optional[str] = None):
        """See your stats in this server. Usage: $me [days]"""
        days = parse_days_arg(days_arg) or 14
        await self._send_user_stats(ctx, ctx.author, days)

    @commands.command(name="user", help="See a user's stats in this server.")
    @commands.guild_only()
    async def user_stats(
        self,
        ctx: commands.Context,
        target_or_days: Optional[str] = None,
        days_arg: Optional[str] = None,
    ):
        """See a user's stats in this server. Usage: $user [@member] [days]"""
        member = ctx.author
        days = 14

        if target_or_days:
            parsed_d = parse_days_arg(target_or_days)
            if parsed_d is not None:
                days = parsed_d
            else:
                try:
                    member = await commands.MemberConverter().convert(ctx, target_or_days)
                except commands.BadArgument:
                    embed = discord.Embed(
                        description=f"{self.cross} **Could not find that member.** Usage: `$user [@member] [days]`",
                        color=discord.Color.red(),
                    )
                    return await ctx.send(embed=embed)

        if days_arg:
            parsed_d2 = parse_days_arg(days_arg)
            if parsed_d2 is not None:
                days = parsed_d2

        await self._send_user_stats(ctx, member, days)

    # ------------------------------------------------------------------
    # 4. $server — See an overview of the server's stats.
    # ------------------------------------------------------------------

    @commands.command(name="server", help="See an overview of the server's stats.")
    @commands.guild_only()
    async def server_stats(self, ctx: commands.Context, days_arg: Optional[str] = None):
        """See an overview of the server's stats. Usage: $server [days]"""
        if not ctx.guild.chunked:
            await ctx.guild.chunk()

        days = parse_days_arg(days_arg) or 14
        self._flush_all_voice_sessions()

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()

            msg_windows = {}
            vc_windows = {}
            for d in (1, 7, 14, 30):
                cutoff = self._window_cutoff(d)
                cur.execute(
                    "SELECT COALESCE(SUM(count), 0) FROM stat_messages WHERE guild_id = ? AND day >= ?",
                    (ctx.guild.id, cutoff),
                )
                msg_windows[d] = cur.fetchone()[0]

                cur.execute(
                    "SELECT COALESCE(SUM(seconds), 0) FROM stat_voice WHERE guild_id = ? AND day >= ?",
                    (ctx.guild.id, cutoff),
                )
                vc_windows[d] = cur.fetchone()[0]

            cutoff_custom = self._window_cutoff(days)

            cur.execute(
                "SELECT COALESCE(SUM(joins), 0), COALESCE(SUM(leaves), 0) FROM stat_member_flow WHERE guild_id = ? AND day >= ?",
                (ctx.guild.id, cutoff_custom),
            )
            joins_total, leaves_total = cur.fetchone()

            cur.execute(
                "SELECT user_id, SUM(count) as total FROM stat_messages WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY total DESC",
                (ctx.guild.id, cutoff_custom),
            )
            msg_users = cur.fetchall()

            cur.execute(
                "SELECT channel_id, SUM(count) as total FROM stat_messages WHERE guild_id = ? AND day >= ? GROUP BY channel_id ORDER BY total DESC",
                (ctx.guild.id, cutoff_custom),
            )
            raw_channels = cur.fetchall()

        active_msg_users = [
            (ctx.guild.get_member(uid), total)
            for uid, total in msg_users
            if ctx.guild.get_member(uid) is not None and not ctx.guild.get_member(uid).bot
        ]
        top_member_str = (
            f"{active_msg_users[0][0].mention} (`{active_msg_users[0][1]:,}` msgs)"
            if active_msg_users
            else "*None yet*"
        )

        top_channel_row = None
        for cid, total in raw_channels:
            ch_obj = ctx.guild.get_channel(cid)
            if ch_obj is not None and not self._is_channel_blacklisted(ch_obj):
                top_channel_row = (cid, total)
                break

        top_channel_str = (
            f"<#{top_channel_row[0]}> (`{top_channel_row[1]:,}` msgs)"
            if top_channel_row
            else "*None yet*"
        )

        humans = sum(1 for m in ctx.guild.members if not m.bot)
        bots = sum(1 for m in ctx.guild.members if m.bot)

        buckets, series = self._get_daily_series(ctx.guild.id, days, table="stat_messages", col="count")
        chart_buf = await asyncio.to_thread(
            self._render_statbot_chart,
            buckets,
            series,
            f"{ctx.guild.name} — Server Activity (Last {days} Days)",
            "Messages",
        )

        embed = discord.Embed(
            title=f"📊 Server Statistics — {ctx.guild.name}",
            description=f"Server-wide telemetry overview (`Last {days} Days`)",
            color=STATBOT_GREEN,
            timestamp=discord.utils.utcnow(),
        )
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        embed.add_field(
            name="💬 Message Totals",
            value=(
                f"• **1d:** `{msg_windows[1]:,}`\n"
                f"• **7d:** `{msg_windows[7]:,}`\n"
                f"• **14d:** `{msg_windows[14]:,}`\n"
                f"• **30d:** `{msg_windows[30]:,}`"
            ),
            inline=True,
        )
        embed.add_field(
            name="🎙️ Voice Totals",
            value=(
                f"• **1d:** `{format_voice_duration(vc_windows[1])}`\n"
                f"• **7d:** `{format_voice_duration(vc_windows[7])}`\n"
                f"• **14d:** `{format_voice_duration(vc_windows[14])}`\n"
                f"• **30d:** `{format_voice_duration(vc_windows[30])}`"
            ),
            inline=True,
        )
        embed.add_field(
            name="👥 Population & Flow",
            value=(
                f"• **Total Members:** `{ctx.guild.member_count:,}` (`{humans:,}` humans, `{bots:,}` bots)\n"
                f"• **Active Messagers ({days}d):** `{len(active_msg_users):,}`\n"
                f"• **Member Flow ({days}d):** `+{joins_total:,}` joined / `-{leaves_total:,}` left (Net `{joins_total - leaves_total:+,}`)"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"🏆 Top Highlights ({days}d)",
            value=(
                f"• **Top Member:** {top_member_str}\n"
                f"• **Top Channel:** {top_channel_str}"
            ),
            inline=False,
        )

        file = discord.File(chart_buf, filename="server_stats.png")
        embed.set_image(url="attachment://server_stats.png")
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed, file=file)

    # ------------------------------------------------------------------
    # 5. $stats — See an overview of a type of stats.
    # ------------------------------------------------------------------

    @commands.command(name="stats", help="See an overview of a type of stats.")
    @commands.guild_only()
    async def stats_type_overview(
        self,
        ctx: commands.Context,
        stat_type: Optional[str] = "messages",
        days_arg: Optional[str] = None,
    ):
        """See an overview of a type of stats. Usage: $stats [messages|voice|members] [days]"""
        if not ctx.guild.chunked:
            await ctx.guild.chunk()

        days = 14
        mode = "messages"

        if stat_type:
            parsed_d = parse_days_arg(stat_type)
            if parsed_d is not None:
                days = parsed_d
            else:
                low = stat_type.lower().strip()
                if low in ("voice", "vc", "audio"):
                    mode = "voice"
                elif low in ("members", "member", "joins", "growth"):
                    mode = "members"
                else:
                    mode = "messages"

        if days_arg:
            parsed_d2 = parse_days_arg(days_arg)
            if parsed_d2 is not None:
                days = parsed_d2

        self._flush_all_voice_sessions()
        cutoff = self._window_cutoff(days)

        if mode == "members":
            buckets = date_buckets(days)
            with sqlite3.connect(self.db_path) as conn:
                rows = {
                    day: (j, l)
                    for day, j, l in conn.execute(
                        "SELECT day, joins, leaves FROM stat_member_flow WHERE guild_id = ? AND day >= ?",
                        (ctx.guild.id, buckets[0]),
                    ).fetchall()
                }
            joins_s = [rows.get(d, (0, 0))[0] for d in buckets]
            leaves_s = [rows.get(d, (0, 0))[1] for d in buckets]

            chart_buf = await asyncio.to_thread(
                self._render_statbot_chart,
                buckets,
                joins_s,
                f"{ctx.guild.name} — Member Stats (Last {days} Days)",
                "Members",
                "#43b581",
                leaves_s,
                "Joins",
                "Leaves",
            )
            embed = discord.Embed(
                title=f"👥 Member Statistics Overview ({days}d)",
                color=STATBOT_GREEN,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Total Members", value=f"`{ctx.guild.member_count:,}`", inline=True)
            embed.add_field(name=f"Joins ({days}d)", value=f"`+{sum(joins_s):,}`", inline=True)
            embed.add_field(name=f"Leaves ({days}d)", value=f"`-{sum(leaves_s):,}`", inline=True)

            file = discord.File(chart_buf, filename="stats_members.png")
            embed.set_image(url="attachment://stats_members.png")
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed, file=file)

        table = "stat_voice" if mode == "voice" else "stat_messages"
        col = "seconds" if mode == "voice" else "count"
        unit_fmt = format_voice_duration if mode == "voice" else (lambda v: f"{v:,} msgs")

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT user_id, SUM({col}) as total FROM {table} WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY total DESC",
                (ctx.guild.id, cutoff),
            )
            raw_users = cur.fetchall()

            cur.execute(
                f"SELECT channel_id, SUM({col}) as total FROM {table} WHERE guild_id = ? AND day >= ? GROUP BY channel_id ORDER BY total DESC",
                (ctx.guild.id, cutoff),
            )
            raw_channels = cur.fetchall()

        active_users = []
        for uid, val in raw_users:
            m = ctx.guild.get_member(uid)
            if m is not None and not m.bot:
                active_users.append((m, val))

        top_channels = []
        for cid, val in raw_channels:
            ch_obj = ctx.guild.get_channel(cid)
            if ch_obj is not None and not self._is_channel_blacklisted(ch_obj):
                top_channels.append((cid, val))
                if len(top_channels) == 5:
                    break

        buckets, series = self._get_daily_series(ctx.guild.id, days, table=table, col=col)
        plot_vals = [round(v / 3600, 2) for v in series] if mode == "voice" else series
        ylabel = "Voice Hours" if mode == "voice" else "Messages"

        chart_buf = await asyncio.to_thread(
            self._render_statbot_chart,
            buckets,
            plot_vals,
            f"{ctx.guild.name} — {'Voice' if mode == 'voice' else 'Message'} Stats (Last {days} Days)",
            ylabel,
            "#3880d4" if mode == "voice" else "#43b581",
        )

        total_val = sum(series)
        embed = discord.Embed(
            title=f"{'🎙️ Voice' if mode == 'voice' else '💬 Message'} Statistics Overview ({days}d)",
            description=(
                f"• **Total ({days}d):** `{unit_fmt(total_val)}`\n"
                f"• **Daily Average:** `{unit_fmt(int(total_val / max(1, days)))}/day`\n"
                f"• **Active Contributors:** `{len(active_users):,}`"
            ),
            color=STATBOT_BLUE if mode == "voice" else STATBOT_GREEN,
            timestamp=discord.utils.utcnow(),
        )

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        if active_users[:5]:
            u_lines = [
                f"{medals.get(i, f'`#{i}`')} {m.mention} — `{unit_fmt(v)}`"
                for i, (m, v) in enumerate(active_users[:5], start=1)
            ]
            embed.add_field(name=f"🏆 Top Members ({days}d)", value="\n".join(u_lines), inline=True)
        else:
            embed.add_field(name=f"🏆 Top Members ({days}d)", value="*No data yet.*", inline=True)

        if top_channels:
            c_lines = [
                f"{medals.get(i, f'`#{i}`')} <#{cid}> — `{unit_fmt(v)}`"
                for i, (cid, v) in enumerate(top_channels, start=1)
            ]
            embed.add_field(name=f"📌 Top Channels ({days}d)", value="\n".join(c_lines), inline=True)
        else:
            embed.add_field(name=f"📌 Top Channels ({days}d)", value="*No data yet.*", inline=True)

        file = discord.File(chart_buf, filename="stats_overview.png")
        embed.set_image(url="attachment://stats_overview.png")
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed, file=file)

    # ------------------------------------------------------------------
    # 6. $top — See a list of top members and channels.
    # ------------------------------------------------------------------

    @commands.command(name="top", help="See a list of top members and channels.")
    @commands.guild_only()
    async def top_leaderboard(
        self,
        ctx: commands.Context,
        category: Optional[str] = None,
        days_arg: Optional[str] = None,
    ):
        """See a list of top members and channels. Usage: $top [messages|voice|channels] [days]"""
        if not ctx.guild.chunked:
            await ctx.guild.chunk()

        days = 14
        mode = "all"

        if category:
            parsed_d = parse_days_arg(category)
            if parsed_d is not None:
                days = parsed_d
            else:
                low = category.lower().strip()
                if low in ("messages", "message", "msg", "msgs", "users", "members"):
                    mode = "messages"
                elif low in ("voice", "vc", "audio"):
                    mode = "voice"
                elif low in ("channels", "channel", "ch"):
                    mode = "channels"

        if days_arg:
            parsed_d2 = parse_days_arg(days_arg)
            if parsed_d2 is not None:
                days = parsed_d2

        self._flush_all_voice_sessions()
        cutoff = self._window_cutoff(days)
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}

        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id, SUM(count) as total FROM stat_messages WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY total DESC",
                (ctx.guild.id, cutoff),
            )
            raw_msg_users = cur.fetchall()

            cur.execute(
                "SELECT channel_id, SUM(count) as total FROM stat_messages WHERE guild_id = ? AND day >= ? GROUP BY channel_id ORDER BY total DESC",
                (ctx.guild.id, cutoff),
            )
            raw_channels = cur.fetchall()

            cur.execute(
                "SELECT user_id, SUM(seconds) as total FROM stat_voice WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY total DESC",
                (ctx.guild.id, cutoff),
            )
            raw_vc_users = cur.fetchall()

        top_msg_members = []
        for uid, total in raw_msg_users:
            m = ctx.guild.get_member(uid)
            if m is not None and not m.bot:
                top_msg_members.append((m, total))

        top_vc_members = []
        for uid, total in raw_vc_users:
            m = ctx.guild.get_member(uid)
            if m is not None and not m.bot:
                top_vc_members.append((m, total))

        top_channels = []
        for cid, total in raw_channels:
            ch_obj = ctx.guild.get_channel(cid)
            if ch_obj is not None and not self._is_channel_blacklisted(ch_obj):
                top_channels.append((cid, total))

        if mode == "all":
            embed = discord.Embed(
                title=f"🏆 Top Members & Channels — {ctx.guild.name} ({days}d)",
                color=STATBOT_GREEN,
                timestamp=discord.utils.utcnow(),
            )
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            msg_text = (
                "\n".join(
                    f"{medals.get(i, f'`#{i}`')} {m.mention} — `{val:,}` msgs"
                    for i, (m, val) in enumerate(top_msg_members[:10], start=1)
                )
                or "*No message activity yet.*"
            )
            ch_text = (
                "\n".join(
                    f"{medals.get(i, f'`#{i}`')} <#{cid}> — `{val:,}` msgs"
                    for i, (cid, val) in enumerate(top_channels[:5], start=1)
                )
                or "*No channel activity yet.*"
            )
            vc_text = (
                "\n".join(
                    f"{medals.get(i, f'`#{i}`')} {m.mention} — `{format_voice_duration(val)}`"
                    for i, (m, val) in enumerate(top_vc_members[:5], start=1)
                )
                or "*No voice activity yet.*"
            )

            embed.add_field(name=f"💬 Top Members ({days}d)", value=msg_text, inline=False)
            embed.add_field(name=f"📌 Top Text Channels ({days}d)", value=ch_text, inline=True)
            embed.add_field(name=f"🎙️ Top Voice Members ({days}d)", value=vc_text, inline=True)
            embed.set_footer(
                text=f"Tip: Use $top messages, $top channels, or $top voice • Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
            return await ctx.send(embed=embed)

        if mode == "messages":
            title = f"🏆 Top Message Members ({days}d)"
            lines = [
                f"{medals.get(i, f'`#{i}`')} {m.mention} — **`{val:,}`** messages"
                for i, (m, val) in enumerate(top_msg_members, start=1)
            ]
        elif mode == "voice":
            title = f"🎙️ Top Voice Members ({days}d)"
            lines = [
                f"{medals.get(i, f'`#{i}`')} {m.mention} — **`{format_voice_duration(val)}`**"
                for i, (m, val) in enumerate(top_vc_members, start=1)
            ]
        else:
            title = f"📌 Top Active Channels ({days}d)"
            lines = [
                f"{medals.get(i, f'`#{i}`')} <#{cid}> — **`{val:,}`** messages"
                for i, (cid, val) in enumerate(top_channels, start=1)
            ]

        if not lines:
            embed = discord.Embed(
                title=title,
                description="No activity recorded for this timeframe yet.",
                color=STATBOT_GREEN,
            )
            return await ctx.send(embed=embed)

        items_per_page = 10
        pages = [lines[i:i + items_per_page] for i in range(0, len(lines), items_per_page)]
        total_pages = len(pages)

        def build_page_embed(page_idx: int) -> discord.Embed:
            embed = discord.Embed(
                title=title,
                description="\n".join(pages[page_idx]),
                color=STATBOT_GREEN,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(
                text=f"Page {page_idx + 1} of {total_pages} • Total Entries: {len(lines)} • Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
            return embed

        class TopPaginationView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60.0)
                self.index = 0
                self.message = None
                self.update_buttons()

            def update_buttons(self):
                self.prev_btn.disabled = self.index == 0
                self.next_btn.disabled = self.index == total_pages - 1

            @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.blurple)
            async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("Only the command author can turn pages.", ephemeral=True)
                self.index -= 1
                self.update_buttons()
                await interaction.response.edit_message(embed=build_page_embed(self.index), view=self)

            @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.blurple)
            async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    return await interaction.response.send_message("Only the command author can turn pages.", ephemeral=True)
                self.index += 1
                self.update_buttons()
                await interaction.response.edit_message(embed=build_page_embed(self.index), view=self)

            async def on_timeout(self):
                for child in self.children:
                    child.disabled = True
                if self.message:
                    try:
                        await self.message.edit(view=self)
                    except discord.HTTPException:
                        pass

        view = TopPaginationView() if total_pages > 1 else None
        sent = await ctx.send(embed=build_page_embed(0), view=view)
        if view:
            view.message = sent


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStats(bot))
