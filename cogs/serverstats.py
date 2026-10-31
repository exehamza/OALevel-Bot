import asyncio
import io
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import aiohttp
import discord
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "database.sqlite")
BLACKLIST_JSON_PATH = os.path.join(BASE_DIR, "data", "serverstats_blacklist.json")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# 2x Retina Render Scale (1920x1120 output)
S = 2

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

# Statbot Palette (RGBA)
BG_DARK = (24, 25, 28, 255)        # #18191c
CARD_BG = (35, 36, 40, 255)        # #232428
CARD_INNER = (43, 45, 49, 255)     # #2b2d31
CARD_BORDER = (56, 58, 64, 255)    # #383a40
TEXT_WHITE = (242, 243, 245, 255)  # #f2f3f5
TEXT_MUTED = (181, 186, 193, 255)  # #b5bac1
TEXT_DIM = (148, 155, 164, 255)    # #949ba4
SB_GREEN = (67, 181, 129, 255)     # #43b581
SB_BLUE = (56, 128, 212, 255)      # #3880d4
SB_GOLD = (250, 166, 26, 255)      # #faa61a
SB_RED = (237, 66, 69, 255)        # #ed4245


def load_font(filename: str, size: int) -> ImageFont.FreeTypeFont:
    font_path = os.path.join(BASE_DIR, "fonts", filename)
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    for fallback in (filename, "DejaVuSans-Bold.ttf" if "Bold" in filename else "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(fallback, size)
        except OSError:
            continue
    return ImageFont.load_default()


def today_bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def date_buckets(days: int) -> list[str]:
    now = datetime.now(timezone.utc)
    return [
        (now - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(days - 1, -1, -1)
    ]


def parse_days_arg(arg: Optional[str]) -> Optional[int]:
    if not arg:
        return None
    cleaned = arg.strip().lower()
    match = re.fullmatch(r"(\d{1,3})d?", cleaned)
    if not match:
        return None
    return max(1, min(int(match.group(1)), 90))


# Singular / Plural Formatting Helpers
def fmt_days(d: int, *, caps: bool = False) -> str:
    unit = "DAY" if d == 1 else "DAYS"
    if not caps:
        unit = unit.title()
    return f"{d} {unit}"


def fmt_msgs(n: int) -> str:
    return f"{n:,} msg" if n == 1 else f"{n:,} msgs"


def fmt_users(n: int, word: str = "user") -> str:
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def format_voice_hours(seconds: int) -> str:
    hrs = max(0, seconds) / 3600.0
    if hrs == 0:
        return "0.00 hrs"
    if hrs < 0.01:
        return "0.01 hrs"
    if abs(hrs - 1.0) < 0.005:
        return "1.00 hr"
    return f"{hrs:,.2f} hrs"


def format_voice_short(seconds: int) -> str:
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


def fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width_px: int) -> str:
    if draw.textlength(text, font=font) <= max_width_px:
        return text
    while len(text) > 3 and draw.textlength(text + "…", font=font) > max_width_px:
        text = text[:-1]
    return text + "…"


def draw_fitted_text(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    *,
    font_file: str = "Arial-Bold.TTF",
    max_size: int = 20,
    min_size: int = 11,
    max_width: int = 300,
    fill=TEXT_WHITE,
    align_right: bool = False,
):
    """Automatically scales font size down so text fits without '...' truncation whenever possible."""
    target_w = max_width * S
    size = max_size * S
    min_s = min_size * S
    font = load_font(font_file, size)

    while size > min_s and draw.textlength(text, font=font) > target_w:
        size -= 1
        font = load_font(font_file, size)

    final_text = fit_text(draw, text, font, target_w)
    y_offset = ((max_size * S) - size) // 2
    draw_x = (x * S - draw.textlength(final_text, font=font)) if align_right else (x * S)
    draw.text((draw_x, y * S + y_offset), final_text, fill=fill, font=font)


# ----------------------------------------------------------------------
# Interactive Statbot Views (Chart <-> Overview, Refresh, Lookback, Select)
# ----------------------------------------------------------------------


class StatTypeSelect(discord.ui.Select):
    def __init__(self, parent_view: "StatbotInteractiveView"):
        self.parent_view = parent_view
        if parent_view.context_kind in ("user", "channel"):
            options = [
                discord.SelectOption(
                    label="Messages",
                    value="messages",
                    description="View message activity statistics",
                    emoji="💬",
                    default=(parent_view.stat_type == "messages"),
                ),
                discord.SelectOption(
                    label="Voice",
                    value="voice",
                    description="View voice activity statistics",
                    emoji="🎙️",
                    default=(parent_view.stat_type == "voice"),
                ),
            ]
        else:
            options = [
                discord.SelectOption(
                    label="Messages",
                    value="messages",
                    description="Server-wide message activity",
                    emoji="💬",
                    default=(parent_view.stat_type == "messages"),
                ),
                discord.SelectOption(
                    label="Voice",
                    value="voice",
                    description="Server-wide voice activity",
                    emoji="🎙️",
                    default=(parent_view.stat_type == "voice"),
                ),
                discord.SelectOption(
                    label="Members",
                    value="members",
                    description="Server member joins & leaves",
                    emoji="👥",
                    default=(parent_view.stat_type == "members"),
                ),
            ]
        super().__init__(placeholder="Select stat type...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.author_id:
            return await interaction.response.send_message(
                "Only the user who ran this command can interact with these controls.", ephemeral=True
            )
        self.parent_view.stat_type = self.values[0]
        await self.parent_view.refresh_message(interaction)


class StatbotInteractiveView(discord.ui.View):
    """Interactive View for $user, $me, $channel, $server, $stats, and $chart."""

    def __init__(
        self,
        cog: "ServerStats",
        ctx: commands.Context,
        *,
        context_kind: str,
        display_mode: str,
        stat_type: str = "messages",
        days: int = 14,
        target_member: Optional[discord.Member] = None,
        target_channel: Optional[discord.abc.GuildChannel] = None,
    ):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.context_kind = context_kind
        self.display_mode = display_mode
        self.stat_type = stat_type
        self.days = days
        self.target_member = target_member
        self.target_channel = target_channel
        self.message: Optional[discord.Message] = None
        self._rebuild_components()

    def _rebuild_components(self):
        self.clear_items()

        if self.display_mode == "chart" or self.context_kind == "stats":
            self.add_item(StatTypeSelect(self))

        toggle_label = "Overview" if self.display_mode == "chart" else "Chart"
        toggle_emoji = "📊" if self.display_mode == "chart" else "📈"
        toggle_btn = discord.ui.Button(
            label=toggle_label,
            emoji=toggle_emoji,
            style=discord.ButtonStyle.primary,
            row=1,
        )
        toggle_btn.callback = self._on_toggle_mode
        self.add_item(toggle_btn)

        refresh_btn = discord.ui.Button(
            label="Refresh",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        refresh_btn.callback = self._on_refresh
        self.add_item(refresh_btn)

        for lb in (7, 14, 30):
            style = discord.ButtonStyle.success if self.days == lb else discord.ButtonStyle.secondary
            lb_btn = discord.ui.Button(label=f"{lb}d", style=style, row=1)
            lb_btn.callback = self._make_lookback_callback(lb)
            self.add_item(lb_btn)

    def _make_lookback_callback(self, lb_days: int):
        async def _callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                return await interaction.response.send_message(
                    "Only the user who ran this command can interact with these controls.", ephemeral=True
                )
            self.days = lb_days
            await self.refresh_message(interaction)
        return _callback

    async def _on_toggle_mode(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Only the user who ran this command can interact with these controls.", ephemeral=True
            )
        self.display_mode = "overview" if self.display_mode == "chart" else "chart"
        await self.refresh_message(interaction)

    async def _on_refresh(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Only the user who ran this command can interact with these controls.", ephemeral=True
            )
        await self.refresh_message(interaction)

    async def render_current_file(self) -> discord.File:
        buf = await self.cog.render_view_card(
            guild=self.ctx.guild,
            context_kind=self.context_kind,
            display_mode=self.display_mode,
            stat_type=self.stat_type,
            days=self.days,
            target_member=self.target_member,
            target_channel=self.target_channel,
        )
        return discord.File(buf, filename="statbot_card.png")

    async def refresh_message(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self._rebuild_components()
        file = await self.render_current_file()
        await interaction.edit_original_response(attachments=[file], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class TopCategorySelect(discord.ui.Select):
    def __init__(self, parent_view: "TopInteractiveView"):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label="Overview",
                value="overview",
                description="Top members and channels overview",
                emoji="📊",
                default=(parent_view.category == "overview"),
            ),
            discord.SelectOption(
                label="Top Message Members",
                value="messages",
                description="Members ranked by messages sent",
                emoji="💬",
                default=(parent_view.category == "messages"),
            ),
            discord.SelectOption(
                label="Top Text Channels",
                value="channels",
                description="Channels ranked by messages sent",
                emoji="📌",
                default=(parent_view.category == "channels"),
            ),
            discord.SelectOption(
                label="Top Voice Members",
                value="voice",
                description="Members ranked by voice time",
                emoji="🎙️",
                default=(parent_view.category == "voice"),
            ),
            discord.SelectOption(
                label="Top Voice Channels",
                value="voice_channels",
                description="Voice channels ranked by time spent",
                emoji="🔊",
                default=(parent_view.category == "voice_channels"),
            ),
        ]
        super().__init__(placeholder="Select leaderboard view...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.parent_view.author_id:
            return await interaction.response.send_message(
                "Only the user who ran this command can interact with these controls.", ephemeral=True
            )
        self.parent_view.category = self.values[0]
        self.parent_view.page = 0
        await self.parent_view.refresh_message(interaction)


class TopInteractiveView(discord.ui.View):
    """Interactive View for $top."""

    def __init__(self, cog: "ServerStats", ctx: commands.Context, *, category: str = "overview", days: int = 14):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.category = category
        self.days = days
        self.page = 0
        self.total_pages = 1
        self.message: Optional[discord.Message] = None
        self._rebuild_components()

    def _rebuild_components(self):
        self.clear_items()
        self.add_item(TopCategorySelect(self))

        if self.category != "overview":
            prev_btn = discord.ui.Button(
                label="◀",
                style=discord.ButtonStyle.primary,
                disabled=(self.page <= 0),
                row=1,
            )
            prev_btn.callback = self._on_prev
            self.add_item(prev_btn)

            next_btn = discord.ui.Button(
                label="▶",
                style=discord.ButtonStyle.primary,
                disabled=(self.page >= self.total_pages - 1),
                row=1,
            )
            next_btn.callback = self._on_next
            self.add_item(next_btn)

        refresh_btn = discord.ui.Button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
        refresh_btn.callback = self._on_refresh
        self.add_item(refresh_btn)

        for lb in (7, 14, 30):
            style = discord.ButtonStyle.success if self.days == lb else discord.ButtonStyle.secondary
            lb_btn = discord.ui.Button(label=f"{lb}d", style=style, row=1)
            lb_btn.callback = self._make_lookback_callback(lb)
            self.add_item(lb_btn)

    def _make_lookback_callback(self, lb_days: int):
        async def _callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                return await interaction.response.send_message(
                    "Only the user who ran this command can interact with these controls.", ephemeral=True
                )
            self.days = lb_days
            self.page = 0
            await self.refresh_message(interaction)
        return _callback

    async def _on_prev(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Only the user who ran this command can interact with these controls.", ephemeral=True
            )
        self.page = max(0, self.page - 1)
        await self.refresh_message(interaction)

    async def _on_next(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Only the user who ran this command can interact with these controls.", ephemeral=True
            )
        self.page = min(self.total_pages - 1, self.page + 1)
        await self.refresh_message(interaction)

    async def _on_refresh(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Only the user who ran this command can interact with these controls.", ephemeral=True
            )
        await self.refresh_message(interaction)

    async def render_current_file(self) -> discord.File:
        buf, total_pages = await self.cog.render_top_card(
            guild=self.ctx.guild,
            category=self.category,
            days=self.days,
            page=self.page,
        )
        self.total_pages = total_pages
        self._rebuild_components()
        return discord.File(buf, filename="statbot_top.png")

    async def refresh_message(self, interaction: discord.Interaction):
        await interaction.response.defer()
        file = await self.render_current_file()
        await interaction.edit_original_response(attachments=[file], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ----------------------------------------------------------------------
# Main ServerStats Cog
# ----------------------------------------------------------------------


class ServerStats(commands.Cog):
    """Statbot-style Server Statistics: $channel, $chart, $me, $server, $stats, $top, $user."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = DB_PATH
        self.blacklist_path = BLACKLIST_JSON_PATH
        self.tick = "<:Tick:1514986183489360087>"
        self.cross = "<a:Cross:1514986232294281426>"

        self.blacklisted_channels: set[int] = self._load_blacklisted_channels()
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
                    loaded = data.get("blacklisted_channels", []) if isinstance(data, dict) else data
                    if isinstance(loaded, list):
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
                json.dump({"blacklisted_channels": sorted(channels)}, f, indent=2)
                f.write("\n")
        except OSError as e:
            print(f"[ServerStats] Failed to save blacklist JSON: {e}")

    def _is_channel_blacklisted(self, channel) -> bool:
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
    # Database Initialization & Tracking
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
        print(f"ServerStats Dashboard Engine initialized ({len(self.blacklisted_channels)} channels blacklisted).")

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

        if key in self._voice_sessions:
            old_channel_id, started = self._voice_sessions.pop(key)
            elapsed = int(now - started)
            if elapsed > 0 and old_channel_id not in self.blacklisted_channels:
                await asyncio.to_thread(self._record_voice_seconds, member.guild.id, member.id, old_channel_id, elapsed)

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
    # Graphical Helpers (2x Retina PIL + 200 DPI Matplotlib)
    # ------------------------------------------------------------------

    async def _fetch_avatar_image(self, url: Optional[str], size: int = 60) -> Optional[Image.Image]:
        if not url:
            return None
        target_px = size * S
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        raw = await resp.read()
                        img = Image.open(io.BytesIO(raw)).convert("RGBA")
                        return img.resize((target_px, target_px), Image.Resampling.LANCZOS)
        except Exception:
            return None
        return None

    @staticmethod
    def _paste_circular_icon(
        canvas: Image.Image,
        icon: Optional[Image.Image],
        x: int,
        y: int,
        size: int = 60,
        badge_text: str = "#",
    ):
        px, py, psize = x * S, y * S, size * S
        draw = ImageDraw.Draw(canvas)
        if icon is not None:
            # 4x supersampled anti-aliased circular mask
            mask_big = Image.new("L", (psize * 2, psize * 2), 0)
            ImageDraw.Draw(mask_big).ellipse((0, 0, psize * 2, psize * 2), fill=255)
            mask = mask_big.resize((psize, psize), Image.Resampling.LANCZOS)
            canvas.paste(icon, (px, py), mask=mask)
        else:
            draw.ellipse((px, py, px + psize, py + psize), fill=CARD_INNER, outline=SB_GREEN, width=2 * S)
            f_badge = load_font("Arial-Bold.TTF", int(psize * 0.48))
            tw = draw.textlength(badge_text, font=f_badge)
            draw.text((px + (psize - tw) / 2, py + psize * 0.22), badge_text, fill=SB_GREEN, font=f_badge)

    @staticmethod
    def _draw_bento_box(
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        w: int,
        h: int,
        title: Optional[str] = None,
        accent=SB_GREEN,
    ):
        draw.rounded_rectangle(
            [x * S, y * S, (x + w) * S, (y + h) * S],
            radius=14 * S,
            fill=CARD_BG,
            outline=CARD_BORDER,
            width=1 * S,
        )
        if title:
            draw.rounded_rectangle(
                [(x + 14) * S, (y + 14) * S, (x + 18) * S, (y + 34) * S],
                radius=2 * S,
                fill=accent,
            )
            draw_fitted_text(
                draw,
                x + 26,
                y + 13,
                title,
                font_file="Arial-Bold.TTF",
                max_size=17,
                min_size=12,
                max_width=w - 38,
                fill=TEXT_WHITE,
            )

    @staticmethod
    def _draw_header(
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        *,
        title: str,
        subtitle: str,
        days: int,
        icon: Optional[Image.Image] = None,
        badge_text: str = "#",
    ):
        ServerStats._paste_circular_icon(canvas, icon, 28, 22, 60, badge_text=badge_text)

        # Draw Lookback pill on top-right first so we know exact available width for Title
        f_pill = load_font("Arial-Bold.TTF", 14 * S)
        pill_text = f"LOOKBACK: {fmt_days(days, caps=True)}"
        pw_px = int(draw.textlength(pill_text, font=f_pill)) + 28 * S
        px_px = (960 - 28) * S - pw_px
        py_px = 28 * S
        draw.rounded_rectangle(
            [px_px, py_px, px_px + pw_px, py_px + 34 * S],
            radius=10 * S,
            fill=CARD_BG,
            outline=SB_GREEN,
            width=1 * S,
        )
        draw.text((px_px + 14 * S, py_px + 8 * S), pill_text, fill=SB_GREEN, font=f_pill)

        # Dynamically fit Title in the exact space between icon (x=102) and Lookback pill
        available_title_w = int((px_px - 102 * S - 16 * S) / S)
        draw_fitted_text(
            draw,
            102,
            24,
            title,
            font_file="Arial-Bold.TTF",
            max_size=27,
            min_size=14,
            max_width=available_title_w,
            fill=TEXT_WHITE,
        )
        draw_fitted_text(
            draw,
            102,
            59,
            subtitle,
            font_file="Arial.TTF",
            max_size=15,
            min_size=11,
            max_width=available_title_w,
            fill=TEXT_MUTED,
        )

    @staticmethod
    def _render_plot_image(
        days_list: list[str],
        values: list[float],
        *,
        width_px: int,
        height_px: int,
        ylabel: str = "Messages",
        color: str = "#43b581",
        secondary_values: Optional[list[float]] = None,
        primary_label: Optional[str] = None,
        secondary_label: Optional[str] = None,
    ) -> Image.Image:
        dates = [datetime.strptime(d, "%Y-%m-%d") for d in days_list]
        dpi = 100 * S
        fig, ax = plt.subplots(figsize=(width_px / 100.0, height_px / 100.0), dpi=dpi)
        fig.patch.set_facecolor("#232428")
        ax.set_facecolor("#18191c")

        ms = 4.5 if len(dates) <= 16 else 3.0
        ax.plot(dates, values, color=color, linewidth=2.4, marker="o", markersize=ms, label=primary_label)
        ax.fill_between(dates, values, color=color, alpha=0.22)

        if secondary_values is not None:
            ax.plot(
                dates,
                secondary_values,
                color="#ed4245",
                linewidth=2.2,
                marker="o",
                markersize=ms,
                label=secondary_label,
            )
            ax.fill_between(dates, secondary_values, color="#ed4245", alpha=0.16)
            ax.legend(facecolor="#232428", edgecolor="#383a40", labelcolor="#f2f3f5", fontsize=8.5, loc="upper left")

        ax.set_ylabel(ylabel, color="#b5bac1", fontsize=9.5)
        ax.grid(True, linestyle="--", linewidth=0.6, color="#383a40", alpha=0.75)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#383a40")
        ax.spines["bottom"].set_color("#383a40")
        ax.tick_params(axis="x", colors="#b5bac1", labelsize=8)
        ax.tick_params(axis="y", colors="#b5bac1", labelsize=8)

        max_v = max(values + (secondary_values or [0]), default=0)
        ax.set_ylim(bottom=0, top=max(5, max_v * 1.18))

        step = max(1, len(dates) // 6)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=step))

        plt.tight_layout(pad=0.8)
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor(), edgecolor="none")
        buf.seek(0)
        plt.close(fig)
        return Image.open(buf).convert("RGBA")

    # ------------------------------------------------------------------
    # SQLite Data Queries
    # ------------------------------------------------------------------

    def _window_cutoff(self, days: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days - 1)).strftime("%Y-%m-%d")

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
    # Card Builders (User, Channel, Server, Stats, Chart, Top)
    # ------------------------------------------------------------------

    async def render_view_card(
        self,
        *,
        guild: discord.Guild,
        context_kind: str,
        display_mode: str,
        stat_type: str,
        days: int,
        target_member: Optional[discord.Member] = None,
        target_channel: Optional[discord.abc.GuildChannel] = None,
    ) -> io.BytesIO:
        if not guild.chunked:
            await guild.chunk()

        if display_mode == "chart":
            return await self._build_chart_card(
                guild=guild,
                context_kind=context_kind,
                stat_type=stat_type,
                days=days,
                target_member=target_member,
                target_channel=target_channel,
            )

        if context_kind == "user" and target_member is not None:
            return await self._build_user_overview_card(guild, target_member, days)
        if context_kind == "channel" and target_channel is not None:
            return await self._build_channel_overview_card(guild, target_channel, days)
        if context_kind == "stats":
            return await self._build_stats_type_card(guild, stat_type, days)
        return await self._build_server_overview_card(guild, days)

    async def _build_user_overview_card(self, guild: discord.Guild, member: discord.Member, days: int) -> io.BytesIO:
        avatar_img = await self._fetch_avatar_image(member.display_avatar.url, 60)
        self._flush_all_voice_sessions()

        def _query():
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                msg_w, vc_w = {}, {}
                for d in (1, 7, days):
                    c = self._window_cutoff(d)
                    cur.execute(
                        "SELECT COALESCE(SUM(count), 0) FROM stat_messages WHERE guild_id = ? AND user_id = ? AND day >= ?",
                        (guild.id, member.id, c),
                    )
                    msg_w[d] = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COALESCE(SUM(seconds), 0) FROM stat_voice WHERE guild_id = ? AND user_id = ? AND day >= ?",
                        (guild.id, member.id, c),
                    )
                    vc_w[d] = cur.fetchone()[0]

                cutoff_d = self._window_cutoff(days)
                cur.execute(
                    "SELECT user_id, SUM(count) as t FROM stat_messages WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY t DESC",
                    (guild.id, cutoff_d),
                )
                m_rank = None
                idx = 1
                for uid, _ in cur.fetchall():
                    m = guild.get_member(uid)
                    if m and not m.bot:
                        if uid == member.id:
                            m_rank = idx
                            break
                        idx += 1

                cur.execute(
                    "SELECT user_id, SUM(seconds) as t FROM stat_voice WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY t DESC",
                    (guild.id, cutoff_d),
                )
                v_rank = None
                idx = 1
                for uid, _ in cur.fetchall():
                    m = guild.get_member(uid)
                    if m and not m.bot:
                        if uid == member.id:
                            v_rank = idx
                            break
                        idx += 1

                cur.execute(
                    "SELECT channel_id, SUM(count) as t FROM stat_messages WHERE guild_id = ? AND user_id = ? AND day >= ? GROUP BY channel_id ORDER BY t DESC",
                    (guild.id, member.id, cutoff_d),
                )
                top_ch = []
                for cid, cnt in cur.fetchall():
                    ch = guild.get_channel(cid)
                    if ch and not self._is_channel_blacklisted(ch):
                        top_ch.append((ch.name, cnt))
                        if len(top_ch) == 5:
                            break
                return msg_w, vc_w, m_rank, v_rank, top_ch

        msg_w, vc_w, m_rank, v_rank, top_ch = await asyncio.to_thread(_query)
        buckets, series = await asyncio.to_thread(
            self._get_daily_series, guild.id, days, table="stat_messages", col="count", user_id=member.id
        )

        def _draw_card() -> io.BytesIO:
            canvas = Image.new("RGBA", (960 * S, 560 * S), BG_DARK)
            draw = ImageDraw.Draw(canvas)
            self._draw_header(
                canvas,
                draw,
                title=f"{member.display_name} (@{member.name})",
                subtitle=f"Member Statistics • {guild.name} • Timezone: UTC",
                days=days,
                icon=avatar_img,
            )

            self._draw_bento_box(draw, 28, 96, 288, 128, f"Server Ranks ({days}d)", SB_GOLD)
            self._draw_bento_box(draw, 336, 96, 288, 128, "Messages Sent", SB_GREEN)
            self._draw_bento_box(draw, 644, 96, 288, 128, "Voice Activity", SB_BLUE)

            draw_fitted_text(draw, 46, 146, "Message Rank", font_file="Arial.TTF", max_size=15, min_size=12, max_width=140, fill=TEXT_MUTED)
            draw_fitted_text(draw, 300, 143, f"#{m_rank}" if m_rank else "Unranked", max_size=20, min_size=14, max_width=110, fill=SB_GREEN, align_right=True)
            draw_fitted_text(draw, 46, 182, "Voice Rank", font_file="Arial.TTF", max_size=15, min_size=12, max_width=140, fill=TEXT_MUTED)
            draw_fitted_text(draw, 300, 179, f"#{v_rank}" if v_rank else "Unranked", max_size=20, min_size=14, max_width=110, fill=SB_BLUE, align_right=True)

            for idx, (label, d_key) in enumerate([("24 Hours", 1), ("7 Days", 7), (fmt_days(days), days)]):
                yy = 142 + idx * 25
                draw_fitted_text(draw, 354, yy, label, font_file="Arial.TTF", max_size=15, min_size=12, max_width=110, fill=TEXT_MUTED)
                draw_fitted_text(draw, 606, yy, fmt_msgs(msg_w.get(d_key, 0)), max_size=15, min_size=12, max_width=135, fill=TEXT_WHITE, align_right=True)

                draw_fitted_text(draw, 662, yy, label, font_file="Arial.TTF", max_size=15, min_size=12, max_width=110, fill=TEXT_MUTED)
                draw_fitted_text(draw, 914, yy, format_voice_hours(vc_w.get(d_key, 0)), max_size=15, min_size=12, max_width=135, fill=TEXT_WHITE, align_right=True)

            self._draw_bento_box(draw, 28, 240, 360, 292, f"Most Active Channels ({days}d)", SB_GREEN)
            if top_ch:
                max_c = max(top_ch[0][1], 1)
                for i, (ch_name, cnt) in enumerate(top_ch):
                    ry = 286 + i * 46
                    draw.rounded_rectangle([44 * S, ry * S, 372 * S, (ry + 36) * S], radius=8 * S, fill=CARD_INNER)
                    bar_w = int(328 * S * (cnt / max_c))
                    if bar_w > 6 * S:
                        draw.rounded_rectangle([44 * S, (ry + 32) * S, 44 * S + bar_w, (ry + 36) * S], radius=2 * S, fill=SB_GREEN)
                    draw_fitted_text(draw, 54, ry + 8, f"#{i + 1}  #{ch_name}", max_size=14, min_size=10, max_width=225, fill=TEXT_WHITE)
                    draw_fitted_text(draw, 362, ry + 8, f"{cnt:,}", max_size=14, min_size=11, max_width=75, fill=SB_GREEN, align_right=True)
            else:
                draw_fitted_text(draw, 48, 365, "No channel activity recorded yet.", font_file="Arial.TTF", max_size=15, min_size=12, max_width=320, fill=TEXT_DIM)

            self._draw_bento_box(draw, 404, 240, 528, 292, f"Message Activity ({days}d)", SB_GREEN)
            plot_img = self._render_plot_image(buckets, series, width_px=500, height_px=235, ylabel="Messages")
            canvas.paste(plot_img, (418 * S, 284 * S))

            out = io.BytesIO()
            canvas.save(out, format="PNG")
            out.seek(0)
            return out

        return await asyncio.to_thread(_draw_card)

    async def _build_channel_overview_card(
        self, guild: discord.Guild, channel: discord.abc.GuildChannel, days: int
    ) -> io.BytesIO:
        icon_img = await self._fetch_avatar_image(guild.icon.url if guild.icon else None, 60)
        is_voice = isinstance(channel, (discord.VoiceChannel, discord.StageChannel))
        table = "stat_voice" if is_voice else "stat_messages"
        col = "seconds" if is_voice else "count"
        self._flush_all_voice_sessions()

        def _query():
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                windows = {}
                for d in (1, 7, days):
                    c = self._window_cutoff(d)
                    cur.execute(
                        f"SELECT COALESCE(SUM({col}), 0) FROM {table} WHERE guild_id = ? AND channel_id = ? AND day >= ?",
                        (guild.id, channel.id, c),
                    )
                    windows[d] = cur.fetchone()[0]

                cutoff_d = self._window_cutoff(days)
                cur.execute(
                    f"SELECT channel_id, SUM({col}) as t FROM {table} WHERE guild_id = ? AND day >= ? GROUP BY channel_id ORDER BY t DESC",
                    (guild.id, cutoff_d),
                )
                ch_rank = None
                idx = 1
                for cid, _ in cur.fetchall():
                    ch_obj = guild.get_channel(cid)
                    if ch_obj and not self._is_channel_blacklisted(ch_obj):
                        if cid == channel.id:
                            ch_rank = idx
                            break
                        idx += 1

                cur.execute(
                    f"SELECT user_id, SUM({col}) as t FROM {table} WHERE guild_id = ? AND channel_id = ? AND day >= ? GROUP BY user_id ORDER BY t DESC",
                    (guild.id, channel.id, cutoff_d),
                )
                contributors = []
                for uid, val in cur.fetchall():
                    m = guild.get_member(uid)
                    if m and not m.bot:
                        contributors.append((m.display_name, val))
                return windows, ch_rank, contributors

        windows, ch_rank, contributors = await asyncio.to_thread(_query)
        buckets, series = await asyncio.to_thread(
            self._get_daily_series, guild.id, days, table=table, col=col, channel_id=channel.id
        )

        def _draw_card() -> io.BytesIO:
            canvas = Image.new("RGBA", (960 * S, 560 * S), BG_DARK)
            draw = ImageDraw.Draw(canvas)
            accent = SB_BLUE if is_voice else SB_GREEN
            self._draw_header(
                canvas,
                draw,
                title=f"#{channel.name}",
                subtitle=f"{'Voice' if is_voice else 'Text'} Channel Statistics • {guild.name}",
                days=days,
                icon=icon_img,
                badge_text="VC" if is_voice else "#",
            )

            self._draw_bento_box(draw, 28, 96, 288, 128, "Channel Standing", SB_GOLD)
            self._draw_bento_box(draw, 336, 96, 288, 128, "Activity Totals", accent)
            self._draw_bento_box(draw, 644, 96, 288, 128, "Engagement", accent)

            unit_fn = format_voice_hours if is_voice else fmt_msgs

            draw_fitted_text(draw, 46, 146, f"Rank ({days}d)", font_file="Arial.TTF", max_size=15, min_size=12, max_width=130, fill=TEXT_MUTED)
            draw_fitted_text(draw, 300, 143, f"#{ch_rank}" if ch_rank else "Unranked", max_size=20, min_size=14, max_width=110, fill=SB_GOLD, align_right=True)
            draw_fitted_text(draw, 46, 182, "Channel Type", font_file="Arial.TTF", max_size=15, min_size=12, max_width=130, fill=TEXT_MUTED)
            draw_fitted_text(draw, 300, 182, "Voice" if is_voice else "Text", max_size=15, min_size=12, max_width=110, fill=TEXT_WHITE, align_right=True)

            for idx, (label, d_key) in enumerate([("24 Hours", 1), ("7 Days", 7), (fmt_days(days), days)]):
                yy = 142 + idx * 25
                draw_fitted_text(draw, 354, yy, label, font_file="Arial.TTF", max_size=15, min_size=12, max_width=110, fill=TEXT_MUTED)
                draw_fitted_text(draw, 606, yy, unit_fn(windows.get(d_key, 0)), max_size=15, min_size=12, max_width=135, fill=TEXT_WHITE, align_right=True)

            total_d = windows.get(days, 0)
            daily_avg = unit_fn(int(total_d / max(1, days)))
            draw_fitted_text(draw, 662, 146, "Contributors", font_file="Arial.TTF", max_size=15, min_size=12, max_width=120, fill=TEXT_MUTED)
            draw_fitted_text(draw, 914, 146, fmt_users(len(contributors), "user"), max_size=15, min_size=12, max_width=130, fill=accent, align_right=True)
            draw_fitted_text(draw, 662, 182, "Daily Average", font_file="Arial.TTF", max_size=15, min_size=12, max_width=120, fill=TEXT_MUTED)
            draw_fitted_text(draw, 914, 182, daily_avg, max_size=15, min_size=12, max_width=130, fill=TEXT_WHITE, align_right=True)

            self._draw_bento_box(draw, 28, 240, 360, 292, f"Top Channel Members ({days}d)", accent)
            top_5 = contributors[:5]
            if top_5:
                max_v = max(top_5[0][1], 1)
                for i, (m_name, val) in enumerate(top_5):
                    ry = 286 + i * 46
                    draw.rounded_rectangle([44 * S, ry * S, 372 * S, (ry + 36) * S], radius=8 * S, fill=CARD_INNER)
                    bar_w = int(328 * S * (val / max_v))
                    if bar_w > 6 * S:
                        draw.rounded_rectangle([44 * S, (ry + 32) * S, 44 * S + bar_w, (ry + 36) * S], radius=2 * S, fill=accent)
                    draw_fitted_text(draw, 54, ry + 8, f"#{i + 1}  {m_name}", max_size=14, min_size=10, max_width=220, fill=TEXT_WHITE)
                    val_s = format_voice_short(val) if is_voice else f"{val:,}"
                    draw_fitted_text(draw, 362, ry + 8, val_s, max_size=14, min_size=11, max_width=80, fill=accent, align_right=True)
            else:
                draw_fitted_text(draw, 48, 365, "No activity in this timeframe.", font_file="Arial.TTF", max_size=15, min_size=12, max_width=320, fill=TEXT_DIM)

            self._draw_bento_box(draw, 404, 240, 528, 292, f"Channel Activity ({days}d)", accent)
            plot_vals = [round(v / 3600.0, 2) for v in series] if is_voice else series
            plot_img = self._render_plot_image(
                buckets,
                plot_vals,
                width_px=500,
                height_px=235,
                ylabel="Hours" if is_voice else "Messages",
                color="#3880d4" if is_voice else "#43b581",
            )
            canvas.paste(plot_img, (418 * S, 284 * S))

            out = io.BytesIO()
            canvas.save(out, format="PNG")
            out.seek(0)
            return out

        return await asyncio.to_thread(_draw_card)

    async def _build_server_overview_card(self, guild: discord.Guild, days: int) -> io.BytesIO:
        icon_img = await self._fetch_avatar_image(guild.icon.url if guild.icon else None, 60)
        self._flush_all_voice_sessions()

        def _query():
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                msg_w, vc_w = {}, {}
                for d in (1, 7, days):
                    c = self._window_cutoff(d)
                    cur.execute(
                        "SELECT COALESCE(SUM(count), 0) FROM stat_messages WHERE guild_id = ? AND day >= ?",
                        (guild.id, c),
                    )
                    msg_w[d] = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COALESCE(SUM(seconds), 0) FROM stat_voice WHERE guild_id = ? AND day >= ?",
                        (guild.id, c),
                    )
                    vc_w[d] = cur.fetchone()[0]

                cutoff_d = self._window_cutoff(days)
                cur.execute(
                    "SELECT COALESCE(SUM(joins), 0), COALESCE(SUM(leaves), 0) FROM stat_member_flow WHERE guild_id = ? AND day >= ?",
                    (guild.id, cutoff_d),
                )
                joins_d, leaves_d = cur.fetchone()

                cur.execute(
                    "SELECT user_id, SUM(count) as t FROM stat_messages WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY t DESC",
                    (guild.id, cutoff_d),
                )
                active_members = []
                for uid, val in cur.fetchall():
                    m = guild.get_member(uid)
                    if m and not m.bot:
                        active_members.append((m.display_name, val))

                cur.execute(
                    "SELECT channel_id, SUM(count) as t FROM stat_messages WHERE guild_id = ? AND day >= ? GROUP BY channel_id ORDER BY t DESC",
                    (guild.id, cutoff_d),
                )
                top_channels = []
                for cid, val in cur.fetchall():
                    ch = guild.get_channel(cid)
                    if ch and not self._is_channel_blacklisted(ch):
                        top_channels.append((ch.name, val))
                        if len(top_channels) == 5:
                            break

                return msg_w, vc_w, joins_d, leaves_d, active_members, top_channels

        msg_w, vc_w, joins_d, leaves_d, active_members, top_channels = await asyncio.to_thread(_query)
        buckets, series = await asyncio.to_thread(
            self._get_daily_series, guild.id, days, table="stat_messages", col="count"
        )

        def _draw_card() -> io.BytesIO:
            canvas = Image.new("RGBA", (960 * S, 560 * S), BG_DARK)
            draw = ImageDraw.Draw(canvas)
            self._draw_header(
                canvas,
                draw,
                title=guild.name,
                subtitle="Server Statistics Overview • Timezone: UTC",
                days=days,
                icon=icon_img,
                badge_text="S",
            )

            self._draw_bento_box(draw, 28, 96, 288, 128, "Server Messages", SB_GREEN)
            self._draw_bento_box(draw, 336, 96, 288, 128, "Server Voice Time", SB_BLUE)
            self._draw_bento_box(draw, 644, 96, 288, 128, f"Population ({days}d)", SB_GOLD)

            for idx, (label, d_key) in enumerate([("24 Hours", 1), ("7 Days", 7), (fmt_days(days), days)]):
                yy = 142 + idx * 25
                draw_fitted_text(draw, 46, yy, label, font_file="Arial.TTF", max_size=15, min_size=12, max_width=110, fill=TEXT_MUTED)
                draw_fitted_text(draw, 298, yy, fmt_msgs(msg_w.get(d_key, 0)), max_size=15, min_size=12, max_width=135, fill=TEXT_WHITE, align_right=True)

                draw_fitted_text(draw, 354, yy, label, font_file="Arial.TTF", max_size=15, min_size=12, max_width=110, fill=TEXT_MUTED)
                draw_fitted_text(draw, 606, yy, format_voice_hours(vc_w.get(d_key, 0)), max_size=15, min_size=12, max_width=135, fill=TEXT_WHITE, align_right=True)

            total_members = guild.member_count or len(guild.members)
            flow_str = f"+{joins_d:,} / -{leaves_d:,}"
            for idx, (label, val_s, col) in enumerate([
                ("Members", f"{total_members:,}", TEXT_WHITE),
                ("Contributors", f"{len(active_members):,} active", SB_GREEN),
                ("Member Flow", flow_str, SB_GOLD),
            ]):
                yy = 142 + idx * 25
                draw_fitted_text(draw, 662, yy, label, font_file="Arial.TTF", max_size=15, min_size=12, max_width=120, fill=TEXT_MUTED)
                draw_fitted_text(draw, 914, yy, val_s, max_size=15, min_size=12, max_width=125, fill=col, align_right=True)

            self._draw_bento_box(draw, 28, 240, 250, 292, f"Top Members ({days}d)", SB_GREEN)
            self._draw_bento_box(draw, 294, 240, 250, 292, f"Top Channels ({days}d)", SB_BLUE)
            self._draw_bento_box(draw, 560, 240, 372, 292, f"Message Activity ({days}d)", SB_GREEN)

            for i, (u_name, cnt) in enumerate(active_members[:5]):
                ry = 286 + i * 46
                draw.rounded_rectangle([42 * S, ry * S, 264 * S, (ry + 36) * S], radius=7 * S, fill=CARD_INNER)
                draw_fitted_text(draw, 50, ry + 9, f"#{i + 1} {u_name}", max_size=13, min_size=10, max_width=145, fill=TEXT_WHITE)
                draw_fitted_text(draw, 256, ry + 9, f"{cnt:,}", max_size=13, min_size=10, max_width=60, fill=SB_GREEN, align_right=True)

            for i, (c_name, cnt) in enumerate(top_channels[:5]):
                ry = 286 + i * 46
                draw.rounded_rectangle([308 * S, ry * S, 530 * S, (ry + 36) * S], radius=7 * S, fill=CARD_INNER)
                draw_fitted_text(draw, 316, ry + 9, f"#{i + 1} #{c_name}", max_size=13, min_size=10, max_width=145, fill=TEXT_WHITE)
                draw_fitted_text(draw, 522, ry + 9, f"{cnt:,}", max_size=13, min_size=10, max_width=60, fill=SB_BLUE, align_right=True)

            plot_img = self._render_plot_image(buckets, series, width_px=348, height_px=235, ylabel="Messages")
            canvas.paste(plot_img, (572 * S, 284 * S))

            out = io.BytesIO()
            canvas.save(out, format="PNG")
            out.seek(0)
            return out

        return await asyncio.to_thread(_draw_card)

    async def _build_stats_type_card(self, guild: discord.Guild, stat_type: str, days: int) -> io.BytesIO:
        icon_img = await self._fetch_avatar_image(guild.icon.url if guild.icon else None, 60)
        self._flush_all_voice_sessions()

        if stat_type == "members":
            return await self._build_chart_card(
                guild=guild, context_kind="stats", stat_type="members", days=days
            )

        is_voice = stat_type == "voice"
        table = "stat_voice" if is_voice else "stat_messages"
        col = "seconds" if is_voice else "count"

        def _query():
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                windows = {}
                for d in (1, 7, days):
                    c = self._window_cutoff(d)
                    cur.execute(f"SELECT COALESCE(SUM({col}), 0) FROM {table} WHERE guild_id = ? AND day >= ?", (guild.id, c))
                    windows[d] = cur.fetchone()[0]

                cutoff_d = self._window_cutoff(days)
                cur.execute(
                    f"SELECT user_id, SUM({col}) as t FROM {table} WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY t DESC",
                    (guild.id, cutoff_d),
                )
                users = []
                for uid, val in cur.fetchall():
                    m = guild.get_member(uid)
                    if m and not m.bot:
                        users.append((m.display_name, val))

                cur.execute(
                    f"SELECT channel_id, SUM({col}) as t FROM {table} WHERE guild_id = ? AND day >= ? GROUP BY channel_id ORDER BY t DESC",
                    (guild.id, cutoff_d),
                )
                channels = []
                for cid, val in cur.fetchall():
                    ch = guild.get_channel(cid)
                    if ch and not self._is_channel_blacklisted(ch):
                        channels.append((ch.name, val))
                        if len(channels) == 5:
                            break
                return windows, users, channels

        windows, users, channels = await asyncio.to_thread(_query)
        buckets, series = await asyncio.to_thread(self._get_daily_series, guild.id, days, table=table, col=col)

        def _draw_card() -> io.BytesIO:
            canvas = Image.new("RGBA", (960 * S, 560 * S), BG_DARK)
            draw = ImageDraw.Draw(canvas)
            accent = SB_BLUE if is_voice else SB_GREEN
            self._draw_header(
                canvas,
                draw,
                title=f"{'Voice' if is_voice else 'Message'} Statistics — {guild.name}",
                subtitle=f"Server {'Voice' if is_voice else 'Message'} Breakdown • Timezone: UTC",
                days=days,
                icon=icon_img,
            )

            self._draw_bento_box(draw, 28, 96, 288, 128, "Timeframe Totals", accent)
            self._draw_bento_box(draw, 336, 96, 288, 128, "Participation", accent)
            self._draw_bento_box(draw, 644, 96, 288, 128, "Top Highlights", SB_GOLD)

            unit_fn = format_voice_hours if is_voice else fmt_msgs

            for idx, (label, d_key) in enumerate([("24 Hours", 1), ("7 Days", 7), (fmt_days(days), days)]):
                yy = 142 + idx * 25
                draw_fitted_text(draw, 46, yy, label, font_file="Arial.TTF", max_size=15, min_size=12, max_width=110, fill=TEXT_MUTED)
                draw_fitted_text(draw, 298, yy, unit_fn(windows.get(d_key, 0)), max_size=15, min_size=12, max_width=135, fill=TEXT_WHITE, align_right=True)

            peak_val = max(series, default=0)
            avg_val = int(windows.get(days, 0) / max(1, days))
            for idx, (label, vs) in enumerate([
                ("Contributors", fmt_users(len(users), "member")),
                ("Daily Average", unit_fn(avg_val)),
                ("Peak Day", unit_fn(peak_val)),
            ]):
                yy = 142 + idx * 25
                draw_fitted_text(draw, 354, yy, label, font_file="Arial.TTF", max_size=15, min_size=12, max_width=115, fill=TEXT_MUTED)
                draw_fitted_text(draw, 606, yy, vs, max_size=15, min_size=12, max_width=130, fill=TEXT_WHITE, align_right=True)

            top_u = users[0][0] if users else "None"
            top_c = f"#{channels[0][0]}" if channels else "None"
            draw_fitted_text(draw, 662, 148, "Top Member", font_file="Arial.TTF", max_size=15, min_size=12, max_width=105, fill=TEXT_MUTED)
            draw_fitted_text(draw, 914, 148, top_u, max_size=15, min_size=11, max_width=145, fill=SB_GOLD, align_right=True)
            draw_fitted_text(draw, 662, 184, "Top Channel", font_file="Arial.TTF", max_size=15, min_size=12, max_width=105, fill=TEXT_MUTED)
            draw_fitted_text(draw, 914, 184, top_c, max_size=15, min_size=11, max_width=145, fill=accent, align_right=True)

            self._draw_bento_box(draw, 28, 240, 250, 292, f"Top Members ({days}d)", accent)
            self._draw_bento_box(draw, 294, 240, 250, 292, f"Top Channels ({days}d)", accent)
            self._draw_bento_box(draw, 560, 240, 372, 292, f"Activity Graph ({days}d)", accent)

            for i, (u_name, val) in enumerate(users[:5]):
                ry = 286 + i * 46
                draw.rounded_rectangle([42 * S, ry * S, 264 * S, (ry + 36) * S], radius=7 * S, fill=CARD_INNER)
                draw_fitted_text(draw, 50, ry + 9, f"#{i + 1} {u_name}", max_size=13, min_size=10, max_width=140, fill=TEXT_WHITE)
                vs = format_voice_short(val) if is_voice else f"{val:,}"
                draw_fitted_text(draw, 256, ry + 9, vs, max_size=13, min_size=10, max_width=65, fill=accent, align_right=True)

            for i, (c_name, val) in enumerate(channels[:5]):
                ry = 286 + i * 46
                draw.rounded_rectangle([308 * S, ry * S, 530 * S, (ry + 36) * S], radius=7 * S, fill=CARD_INNER)
                draw_fitted_text(draw, 316, ry + 9, f"#{i + 1} #{c_name}", max_size=13, min_size=10, max_width=140, fill=TEXT_WHITE)
                vs = format_voice_short(val) if is_voice else f"{val:,}"
                draw_fitted_text(draw, 522, ry + 9, vs, max_size=13, min_size=10, max_width=65, fill=accent, align_right=True)

            plot_vals = [round(v / 3600.0, 2) for v in series] if is_voice else series
            plot_img = self._render_plot_image(
                buckets,
                plot_vals,
                width_px=348,
                height_px=235,
                ylabel="Hours" if is_voice else "Messages",
                color="#3880d4" if is_voice else "#43b581",
            )
            canvas.paste(plot_img, (572 * S, 284 * S))

            out = io.BytesIO()
            canvas.save(out, format="PNG")
            out.seek(0)
            return out

        return await asyncio.to_thread(_draw_card)

    async def _build_chart_card(
        self,
        *,
        guild: discord.Guild,
        context_kind: str,
        stat_type: str,
        days: int,
        target_member: Optional[discord.Member] = None,
        target_channel: Optional[discord.abc.GuildChannel] = None,
    ) -> io.BytesIO:
        if context_kind == "user" and target_member is not None:
            icon_url = target_member.display_avatar.url
        else:
            icon_url = guild.icon.url if guild.icon else None
        icon_img = await self._fetch_avatar_image(icon_url, 60)

        buckets = date_buckets(days)
        secondary_series = None
        primary_label = None
        secondary_label = None

        if stat_type == "members" and context_kind not in ("user", "channel"):
            with sqlite3.connect(self.db_path) as conn:
                rows = {
                    day: (j, l)
                    for day, j, l in conn.execute(
                        "SELECT day, joins, leaves FROM stat_member_flow WHERE guild_id = ? AND day >= ?",
                        (guild.id, buckets[0]),
                    ).fetchall()
                }
            series = [rows.get(d, (0, 0))[0] for d in buckets]
            secondary_series = [rows.get(d, (0, 0))[1] for d in buckets]
            primary_label, secondary_label = "Joins", "Leaves"
            title = f"{guild.name} — Member Flow Chart"
            ylabel = "Members"
            color_hex = "#43b581"
            accent = SB_GREEN
            stat_1 = ("Total Joins", f"+{sum(series):,}")
            stat_2 = ("Total Leaves", f"-{sum(secondary_series):,}")
            stat_3 = ("Net Growth", f"{sum(series) - sum(secondary_series):+,}")
        else:
            is_voice = stat_type == "voice" or (
                context_kind == "channel"
                and isinstance(target_channel, (discord.VoiceChannel, discord.StageChannel))
            )
            table = "stat_voice" if is_voice else "stat_messages"
            col = "seconds" if is_voice else "count"
            uid = target_member.id if (context_kind == "user" and target_member) else None
            cid = target_channel.id if (context_kind == "channel" and target_channel) else None

            buckets, raw_series = await asyncio.to_thread(
                self._get_daily_series, guild.id, days, table=table, col=col, user_id=uid, channel_id=cid
            )
            series = [round(v / 3600.0, 2) for v in raw_series] if is_voice else raw_series
            ylabel = "Voice Hours" if is_voice else "Messages"
            color_hex = "#3880d4" if is_voice else "#43b581"
            accent = SB_BLUE if is_voice else SB_GREEN

            if context_kind == "user" and target_member:
                title = f"@{target_member.name} — {'Voice' if is_voice else 'Message'} Chart"
            elif context_kind == "channel" and target_channel:
                title = f"#{target_channel.name} — {'Voice' if is_voice else 'Message'} Chart"
            else:
                title = f"{guild.name} — {'Voice' if is_voice else 'Message'} Chart"

            total_raw = sum(raw_series)
            unit_fn = format_voice_hours if is_voice else fmt_msgs
            stat_1 = (f"Total ({days}d)", unit_fn(total_raw))
            stat_2 = ("Daily Average", unit_fn(int(total_raw / max(1, days))))
            stat_3 = ("Peak Day", unit_fn(max(raw_series, default=0)))

        def _draw_card() -> io.BytesIO:
            canvas = Image.new("RGBA", (960 * S, 560 * S), BG_DARK)
            draw = ImageDraw.Draw(canvas)
            self._draw_header(
                canvas,
                draw,
                title=title,
                subtitle=f"Detailed Time-Series Chart • Lookback: {fmt_days(days)} • Timezone: UTC",
                days=days,
                icon=icon_img,
            )

            for idx, (lbl, val) in enumerate([stat_1, stat_2, stat_3]):
                bx = 28 + idx * 308
                self._draw_bento_box(draw, bx, 96, 288, 78)
                draw_fitted_text(draw, bx + 20, 110, lbl, font_file="Arial.TTF", max_size=14, min_size=11, max_width=248, fill=TEXT_MUTED)
                draw_fitted_text(draw, bx + 20, 134, val, max_size=22, min_size=14, max_width=248, fill=accent)

            self._draw_bento_box(draw, 28, 188, 904, 344, f"Activity Timeline ({days}d)", accent)
            plot_img = self._render_plot_image(
                buckets,
                series,
                width_px=876,
                height_px=286,
                ylabel=ylabel,
                color=color_hex,
                secondary_values=secondary_series,
                primary_label=primary_label,
                secondary_label=secondary_label,
            )
            canvas.paste(plot_img, (42 * S, 234 * S))

            out = io.BytesIO()
            canvas.save(out, format="PNG")
            out.seek(0)
            return out

        return await asyncio.to_thread(_draw_card)

    async def render_top_card(
        self,
        *,
        guild: discord.Guild,
        category: str,
        days: int,
        page: int = 0,
    ) -> tuple[io.BytesIO, int]:
        if not guild.chunked:
            await guild.chunk()

        icon_img = await self._fetch_avatar_image(guild.icon.url if guild.icon else None, 60)
        self._flush_all_voice_sessions()
        cutoff = self._window_cutoff(days)

        def _query():
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT user_id, SUM(count) as t FROM stat_messages WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY t DESC",
                    (guild.id, cutoff),
                )
                msg_users = [
                    (guild.get_member(uid).display_name, val)
                    for uid, val in cur.fetchall()
                    if guild.get_member(uid) is not None and not guild.get_member(uid).bot
                ]

                cur.execute(
                    "SELECT channel_id, SUM(count) as t FROM stat_messages WHERE guild_id = ? AND day >= ? GROUP BY channel_id ORDER BY t DESC",
                    (guild.id, cutoff),
                )
                msg_channels = [
                    (f"#{guild.get_channel(cid).name}", val)
                    for cid, val in cur.fetchall()
                    if guild.get_channel(cid) is not None and not self._is_channel_blacklisted(guild.get_channel(cid))
                ]

                cur.execute(
                    "SELECT user_id, SUM(seconds) as t FROM stat_voice WHERE guild_id = ? AND day >= ? GROUP BY user_id ORDER BY t DESC",
                    (guild.id, cutoff),
                )
                vc_users = [
                    (guild.get_member(uid).display_name, val)
                    for uid, val in cur.fetchall()
                    if guild.get_member(uid) is not None and not guild.get_member(uid).bot
                ]

                cur.execute(
                    "SELECT channel_id, SUM(seconds) as t FROM stat_voice WHERE guild_id = ? AND day >= ? GROUP BY channel_id ORDER BY t DESC",
                    (guild.id, cutoff),
                )
                vc_channels = [
                    (f"#{guild.get_channel(cid).name}", val)
                    for cid, val in cur.fetchall()
                    if guild.get_channel(cid) is not None and not self._is_channel_blacklisted(guild.get_channel(cid))
                ]
                return msg_users, msg_channels, vc_users, vc_channels

        msg_users, msg_channels, vc_users, vc_channels = await asyncio.to_thread(_query)

        if category == "overview":
            def _draw_overview() -> io.BytesIO:
                canvas = Image.new("RGBA", (960 * S, 560 * S), BG_DARK)
                draw = ImageDraw.Draw(canvas)
                self._draw_header(
                    canvas,
                    draw,
                    title=f"Top Overview — {guild.name}",
                    subtitle=f"Most Active Members & Channels • Lookback: {fmt_days(days)}",
                    days=days,
                    icon=icon_img,
                )

                panels = [
                    (28, 96, f"Top Message Members ({days}d)", msg_users[:4], False, SB_GREEN),
                    (492, 96, f"Top Text Channels ({days}d)", msg_channels[:4], False, SB_GREEN),
                    (28, 324, f"Top Voice Members ({days}d)", vc_users[:4], True, SB_BLUE),
                    (492, 324, f"Top Voice Channels ({days}d)", vc_channels[:4], True, SB_BLUE),
                ]

                for px, py, ptitle, items, is_vc, accent in panels:
                    self._draw_bento_box(draw, px, py, 440, 212, ptitle, accent)
                    if not items:
                        draw_fitted_text(draw, px + 22, py + 100, "No activity recorded yet.", font_file="Arial.TTF", max_size=14, min_size=11, max_width=380, fill=TEXT_DIM)
                        continue
                    max_v = max(items[0][1], 1)
                    for i, (name, val) in enumerate(items):
                        ry = py + 48 + i * 38
                        draw.rounded_rectangle([(px + 16) * S, ry * S, (px + 424) * S, (ry + 32) * S], radius=6 * S, fill=CARD_INNER)
                        bw = int(408 * S * (val / max_v))
                        if bw > 6 * S:
                            draw.rounded_rectangle([(px + 16) * S, (ry + 29) * S, (px + 16) * S + bw, (ry + 32) * S], radius=2 * S, fill=accent)
                        rank_col = SB_GOLD if i == 0 else TEXT_WHITE
                        draw_fitted_text(draw, px + 26, ry + 6, f"#{i + 1}  {name}", max_size=14, min_size=10, max_width=270, fill=rank_col)
                        vs = format_voice_hours(val) if is_vc else fmt_msgs(val)
                        draw_fitted_text(draw, px + 414, ry + 6, vs, max_size=14, min_size=11, max_width=110, fill=accent, align_right=True)

                out = io.BytesIO()
                canvas.save(out, format="PNG")
                out.seek(0)
                return out

            buf = await asyncio.to_thread(_draw_overview)
            return buf, 1

        mapping = {
            "messages": ("Top Message Members", msg_users, False, SB_GREEN),
            "channels": ("Top Text Channels", msg_channels, False, SB_GREEN),
            "voice": ("Top Voice Members", vc_users, True, SB_BLUE),
            "voice_channels": ("Top Voice Channels", vc_channels, True, SB_BLUE),
        }
        title_prefix, full_list, is_vc, accent = mapping.get(category, mapping["messages"])
        per_page = 10
        total_pages = max(1, (len(full_list) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        slice_items = full_list[page * per_page : (page + 1) * per_page]
        global_max = max(full_list[0][1], 1) if full_list else 1

        def _draw_list() -> io.BytesIO:
            canvas = Image.new("RGBA", (960 * S, 560 * S), BG_DARK)
            draw = ImageDraw.Draw(canvas)
            self._draw_header(
                canvas,
                draw,
                title=f"{title_prefix} — {guild.name}",
                subtitle=f"Page {page + 1} of {total_pages} • Total Ranked: {len(full_list)} • Lookback: {fmt_days(days)}",
                days=days,
                icon=icon_img,
            )
            self._draw_bento_box(draw, 28, 96, 904, 436, f"{title_prefix} ({days}d)", accent)

            if not slice_items:
                draw_fitted_text(draw, 54, 290, "No activity recorded for this timeframe yet.", font_file="Arial.TTF", max_size=15, min_size=12, max_width=500, fill=TEXT_DIM)
            else:
                for idx, (name, val) in enumerate(slice_items):
                    rank_num = page * per_page + idx + 1
                    col_idx = idx // 5
                    row_idx = idx % 5
                    rx = 46 + col_idx * 440
                    ry = 148 + row_idx * 72

                    draw.rounded_rectangle([rx * S, ry * S, (rx + 426) * S, (ry + 58) * S], radius=10 * S, fill=CARD_INNER)
                    bw = int(426 * S * (val / global_max))
                    if bw > 8 * S:
                        draw.rounded_rectangle([rx * S, (ry + 53) * S, rx * S + bw, (ry + 58) * S], radius=3 * S, fill=accent)

                    r_col = SB_GOLD if rank_num == 1 else ((192, 198, 206, 255) if rank_num == 2 else ((205, 127, 50, 255) if rank_num == 3 else TEXT_MUTED))
                    draw_fitted_text(draw, rx + 16, ry + 18, f"#{rank_num}", max_size=18, min_size=13, max_width=50, fill=r_col)
                    draw_fitted_text(draw, rx + 68, ry + 19, name, max_size=15, min_size=10, max_width=235, fill=TEXT_WHITE)
                    vs = format_voice_hours(val) if is_vc else fmt_msgs(val)
                    draw_fitted_text(draw, rx + 410, ry + 19, vs, max_size=15, min_size=11, max_width=105, fill=accent, align_right=True)

            out = io.BytesIO()
            canvas.save(out, format="PNG")
            out.seek(0)
            return out

        buf = await asyncio.to_thread(_draw_list)
        return buf, total_pages

    # ------------------------------------------------------------------
    # Commands ($channel, $chart, $me, $server, $stats, $top, $user)
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
        channel = ctx.channel
        days = 14
        mode = "overview"

        if target_or_days:
            if target_or_days.lower() == "chart":
                mode = "chart"
            else:
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
                description=f"{self.cross} **That channel is excluded from Server Statistics.**",
                color=discord.Color.red(),
            )
            return await ctx.send(embed=embed)

        is_vc = isinstance(channel, (discord.VoiceChannel, discord.StageChannel))
        view = StatbotInteractiveView(
            self,
            ctx,
            context_kind="channel",
            display_mode=mode,
            stat_type="voice" if is_vc else "messages",
            days=days,
            target_channel=channel,
        )
        file = await view.render_current_file()
        view.message = await ctx.send(file=file, view=view)

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
        stat_type = "messages"
        context_kind = "server"
        target_member: Optional[discord.Member] = None
        target_channel: Optional[discord.abc.GuildChannel] = None

        for token in [t for t in (arg1, arg2, arg3) if t is not None]:
            low = token.lower().strip()
            parsed_d = parse_days_arg(low)
            if parsed_d is not None:
                days = parsed_d
                continue
            if low in ("messages", "message", "msg", "msgs"):
                stat_type = "messages"
                continue
            if low in ("voice", "vc", "audio"):
                stat_type = "voice"
                continue
            if low in ("members", "member", "joins", "growth"):
                stat_type = "members"
                context_kind = "stats"
                continue
            if low in ("channel", "user"):
                continue

            try:
                target_channel = await commands.GuildChannelConverter().convert(ctx, token)
                context_kind = "channel"
                if isinstance(target_channel, (discord.VoiceChannel, discord.StageChannel)):
                    stat_type = "voice"
                continue
            except commands.BadArgument:
                pass

            try:
                target_member = await commands.MemberConverter().convert(ctx, token)
                context_kind = "user"
                continue
            except commands.BadArgument:
                pass

        if target_channel and self._is_channel_blacklisted(target_channel):
            embed = discord.Embed(
                description=f"{self.cross} **That channel is excluded from Server Statistics.**",
                color=discord.Color.red(),
            )
            return await ctx.send(embed=embed)

        view = StatbotInteractiveView(
            self,
            ctx,
            context_kind=context_kind,
            display_mode="chart",
            stat_type=stat_type,
            days=days,
            target_member=target_member,
            target_channel=target_channel,
        )
        file = await view.render_current_file()
        view.message = await ctx.send(file=file, view=view)

    @commands.command(name="me", help="See your stats in this server.")
    @commands.guild_only()
    async def me_stats(self, ctx: commands.Context, days_arg: Optional[str] = None):
        """See your stats in this server. Usage: $me [days]"""
        days = parse_days_arg(days_arg) or 14
        view = StatbotInteractiveView(
            self,
            ctx,
            context_kind="user",
            display_mode="overview",
            stat_type="messages",
            days=days,
            target_member=ctx.author,
        )
        file = await view.render_current_file()
        view.message = await ctx.send(file=file, view=view)

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
        mode = "overview"

        if target_or_days:
            if target_or_days.lower() == "chart":
                mode = "chart"
            else:
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

        if member.bot:
            embed = discord.Embed(
                description=f"{self.cross} **Bots are excluded from Server Statistics.**",
                color=discord.Color.red(),
            )
            return await ctx.send(embed=embed)

        view = StatbotInteractiveView(
            self,
            ctx,
            context_kind="user",
            display_mode=mode,
            stat_type="messages",
            days=days,
            target_member=member,
        )
        file = await view.render_current_file()
        view.message = await ctx.send(file=file, view=view)

    @commands.command(name="server", help="See an overview of the server's stats.")
    @commands.guild_only()
    async def server_stats(self, ctx: commands.Context, days_arg: Optional[str] = None):
        """See an overview of the server's stats. Usage: $server [days]"""
        days = parse_days_arg(days_arg) or 14
        view = StatbotInteractiveView(
            self,
            ctx,
            context_kind="server",
            display_mode="overview",
            stat_type="messages",
            days=days,
        )
        file = await view.render_current_file()
        view.message = await ctx.send(file=file, view=view)

    @commands.command(name="stats", help="See an overview of a type of stats.")
    @commands.guild_only()
    async def stats_type_overview(
        self,
        ctx: commands.Context,
        stat_type: Optional[str] = "messages",
        days_arg: Optional[str] = None,
    ):
        """See an overview of a type of stats. Usage: $stats [messages|voice|members] [days]"""
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

        if days_arg:
            parsed_d2 = parse_days_arg(days_arg)
            if parsed_d2 is not None:
                days = parsed_d2

        view = StatbotInteractiveView(
            self,
            ctx,
            context_kind="stats",
            display_mode="overview",
            stat_type=mode,
            days=days,
        )
        file = await view.render_current_file()
        view.message = await ctx.send(file=file, view=view)

    @commands.command(name="top", help="See a list of top members and channels.")
    @commands.guild_only()
    async def top_leaderboard(
        self,
        ctx: commands.Context,
        category: Optional[str] = None,
        days_arg: Optional[str] = None,
    ):
        """See a list of top members and channels. Usage: $top [messages|voice|channels] [days]"""
        days = 14
        cat = "overview"

        if category:
            parsed_d = parse_days_arg(category)
            if parsed_d is not None:
                days = parsed_d
            else:
                low = category.lower().strip()
                if low in ("messages", "message", "msg", "msgs", "users", "members"):
                    cat = "messages"
                elif low in ("voice", "vc", "audio"):
                    cat = "voice"
                elif low in ("channels", "channel", "ch"):
                    cat = "channels"

        if days_arg:
            parsed_d2 = parse_days_arg(days_arg)
            if parsed_d2 is not None:
                days = parsed_d2

        view = TopInteractiveView(self, ctx, category=cat, days=days)
        file = await view.render_current_file()
        view.message = await ctx.send(file=file, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStats(bot))
