"""
AutoLogger - Dyno-style message edit/delete, member join/leave, role, and channel logger.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import shutil
import tempfile
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Awaitable, Callable, List, Optional, Set

import aiohttp
import discord
from discord.ext import commands

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

LOG_CHANNEL_ID = 1296530025637740554
IGNORED_CHANNEL_IDS = {LOG_CHANNEL_ID, 1324373003680743503}

DELETE_COLOR = discord.Colour(0xFF4500)  # Dyno orange-red
EDIT_COLOR = discord.Colour(0x3880D4)    # Dyno blue
JOIN_COLOR = discord.Colour(0x43B581)    # Dyno green
LEAVE_COLOR = discord.Colour(0xFF4500)   # Dyno orange-red

CACHE_MAX_ENTRIES = 1000
SEGMENT_MAX = 1024

MAX_IMAGE_DOWNLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
IMAGE_TMP_DIR = Path(tempfile.gettempdir()) / "autologger-images"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

IGNORE_BOTS = True

# --------------------------------------------------------------------------
# Helpers & Views
# --------------------------------------------------------------------------


def truncate(value: str, limit: int = SEGMENT_MAX) -> str:
    if not value:
        return "*(empty)*"
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def format_age(delta: timedelta) -> str:
    """Human-readable duration down to hrs, mins, secs."""
    seconds = max(int(delta.total_seconds()), 0)
    units = (
        ("year", 365 * 86400),
        ("month", 30 * 86400),
        ("day", 86400),
        ("hr", 3600),
        ("min", 60),
        ("sec", 1),
    )
    parts = []
    for name, size in units:
        count, seconds = divmod(seconds, size)
        if count:
            parts.append(f"{count} {name}{'' if count == 1 else 's'}")
    return ", ".join(parts) or "0 secs"


def format_channel_type(channel: discord.abc.GuildChannel) -> str:
    mapping = {
        discord.ChannelType.text: "Text Channel",
        discord.ChannelType.voice: "Voice Channel",
        discord.ChannelType.category: "Category",
        discord.ChannelType.news: "Announcement Channel",
        discord.ChannelType.stage_voice: "Stage Channel",
        discord.ChannelType.forum: "Forum Channel",
    }
    return mapping.get(getattr(channel, "type", None), "Channel")


def remove_file(path: Optional[Path]) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.debug("AutoLogger: could not remove tmp file %s: %s", path, exc)


class MessageLogView(discord.ui.View):
    """Dyno-style action row with 'Get User ID' and 'Jump to Context/Message'."""

    def __init__(self, user_id: int, jump_url: str, *, is_edit: bool) -> None:
        super().__init__(timeout=None)
        # Handled persistently via Cog's on_interaction listener using custom_id
        self.add_item(
            discord.ui.Button(
                label="Get User ID",
                style=discord.ButtonStyle.secondary,
                custom_id=f"autologger:userid:{user_id}",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Jump to Message" if is_edit else "Jump to Context",
                style=discord.ButtonStyle.link,
                url=jump_url,
            )
        )


@dataclass
class CachedImage:
    url: str
    proxy_url: str
    filename: str
    path: Optional[Path] = None


@dataclass
class CachedMessage:
    message_id: int
    channel_id: int
    channel_name: str
    guild_id: int
    author_id: int
    author_name: str
    content: str
    images: List[CachedImage] = field(default_factory=list)
    download_task: Optional["asyncio.Task[None]"] = None


class MessageCache:
    """In-memory LRU cache built on OrderedDict."""

    def __init__(
        self,
        max_entries: int,
        on_evict: Optional[Callable[[CachedMessage], None]] = None,
    ) -> None:
        self._data: "OrderedDict[int, CachedMessage]" = OrderedDict()
        self._max = max_entries
        self._on_evict = on_evict

    def __len__(self) -> int:
        return len(self._data)

    def peek(self, key: int) -> Optional[CachedMessage]:
        return self._data.get(key)

    def get(self, key: int) -> Optional[CachedMessage]:
        entry = self._data.get(key)
        if entry is not None:
            self._data.move_to_end(key)
        return entry

    def set(self, key: int, entry: CachedMessage) -> None:
        self._data[key] = entry
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            _, evicted = self._data.popitem(last=False)
            if self._on_evict:
                self._on_evict(evicted)

    def pop(self, key: int) -> Optional[CachedMessage]:
        return self._data.pop(key, None)

    def clear(self) -> None:
        entries = list(self._data.values())
        self._data.clear()
        if self._on_evict:
            for entry in entries:
                self._on_evict(entry)


# --------------------------------------------------------------------------
# Cog
# --------------------------------------------------------------------------


class AutoLogger(commands.Cog):
    """Logs message edits/deletes, member joins/leaves, role updates, and channel changes."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._cache = MessageCache(CACHE_MAX_ENTRIES, on_evict=self._discard_entry)
        self._tasks: Set["asyncio.Task[None]"] = set()
        self._warned_missing_channel = False

        try:
            shutil.rmtree(IMAGE_TMP_DIR, ignore_errors=True)
            IMAGE_TMP_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("AutoLogger: failed to initialise image tmp directory: %s", exc)

    async def cog_unload(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        self._cache.clear()
        shutil.rmtree(IMAGE_TMP_DIR, ignore_errors=True)

    # ---- persistent button handler ---------------------------------------

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if custom_id.startswith("autologger:userid:"):
            user_id = custom_id.split("autologger:userid:", 1)[1]
            if not interaction.response.is_done():
                await interaction.response.send_message(user_id, ephemeral=True)

    # ---- caching & image pre-fetching ------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self._should_track(message):
            return

        attachments = self._extract_images(message)
        cached_images = [
            CachedImage(
                url=att.url,
                proxy_url=att.proxy_url,
                filename= re.sub(r"[^a-zA-Z0-9._-]", "_", att.filename) or f"image_{idx}.png",
            )
            for idx, att in enumerate(attachments)
        ]

        entry = CachedMessage(
            message_id=message.id,
            channel_id=message.channel.id,
            channel_name=getattr(message.channel, "name", None) or str(message.channel.id),
            guild_id=message.guild.id,  # type: ignore[union-attr]
            author_id=message.author.id,
            author_name=message.author.name,
            content=message.content,
            images=cached_images,
        )
        self._cache.set(message.id, entry)

        if attachments:
            task = self._spawn(self._download_images(entry, attachments))
            entry.download_task = task

    def _should_track(self, message: discord.Message) -> bool:
        if message.guild is None:
            return False
        if message.channel.id in IGNORED_CHANNEL_IDS:
            return False
        if self.bot.user is not None and message.author.id == self.bot.user.id:
            return False
        if IGNORE_BOTS and message.author.bot:
            return False
        return self._is_log_guild(message.guild.id)

    def _is_log_guild(self, guild_id: int) -> bool:
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        log_guild = getattr(log_channel, "guild", None)
        return log_guild is None or log_guild.id == guild_id

    @staticmethod
    def _extract_images(message: discord.Message) -> List[discord.Attachment]:
        found: List[discord.Attachment] = []
        for attachment in message.attachments:
            ctype = (attachment.content_type or "").lower()
            fname = attachment.filename.lower().split("?")[0]
            if ctype.startswith("image/") or fname.endswith(IMAGE_EXTENSIONS):
                if 0 < attachment.size <= MAX_IMAGE_DOWNLOAD_BYTES:
                    found.append(attachment)
        return found

    def _spawn(self, coro: Awaitable[None]) -> "asyncio.Task[None]":
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _download_images(
        self,
        entry: CachedMessage,
        attachments: List[discord.Attachment],
    ) -> None:
        for idx, attachment in enumerate(attachments):
            if idx >= len(entry.images):
                break
            img_meta = entry.images[idx]
            data: Optional[bytes] = None

            # 1. Try Discord media proxy cache first, then direct CDN
            for use_cached in (True, False):
                try:
                    data = await attachment.read(use_cached=use_cached)
                    if data:
                        break
                except discord.DiscordException:
                    continue

            if not data or len(data) > MAX_IMAGE_DOWNLOAD_BYTES:
                continue

            dest = IMAGE_TMP_DIR / f"{entry.message_id}-{idx}-{img_meta.filename}"
            try:
                IMAGE_TMP_DIR.mkdir(parents=True, exist_ok=True)
                await asyncio.get_running_loop().run_in_executor(None, dest.write_bytes, data)
                img_meta.path = dest
            except OSError as exc:
                log.warning("AutoLogger: failed to write tmp image for message %s: %s", entry.message_id, exc)

    async def _fetch_fallback_bytes(self, img_meta: CachedImage) -> Optional[bytes]:
        """If pre-download missed or was cleared, try fetching from proxy_url or url."""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0)"}
        async with aiohttp.ClientSession(headers=headers) as session:
            for target_url in (img_meta.proxy_url, img_meta.url):
                if not target_url:
                    continue
                try:
                    async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            if data and len(data) <= MAX_IMAGE_DOWNLOAD_BYTES:
                                return data
                except Exception:
                    continue
        return None

    @staticmethod
    def _discard_entry(entry: CachedMessage) -> None:
        for img in entry.images:
            remove_file(img.path)

    # ---- edits -----------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.guild_id is None or payload.channel_id in IGNORED_CHANNEL_IDS:
            return

        after = payload.data.get("content")
        if after is None:
            return

        entry = self._cache.get(payload.message_id)
        if entry is None:
            return

        before = entry.content
        if before == after:
            return

        entry.content = after
        jump_url = f"https://discord.com/channels/{entry.guild_id}/{entry.channel_id}/{entry.message_id}"

        embed = self._build_embed(
            title="Message Edited",
            color=EDIT_COLOR,
            entry=entry,
            before=before,
            after=after,
        )
        view = MessageLogView(user_id=entry.author_id, jump_url=jump_url, is_edit=True)
        await self._send(embed, view=view)

    # ---- deletes ---------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id is None or payload.channel_id in IGNORED_CHANNEL_IDS:
            return

        entry = self._cache.pop(payload.message_id)
        if entry is None:
            return

        # If the image download is still running (e.g. fast delete), wait for it to finish!
        if entry.download_task is not None and not entry.download_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(entry.download_task), timeout=8.0)
            except (asyncio.TimeoutError, Exception):
                pass

        files: List[discord.File] = []
        for img_meta in entry.images:
            data: Optional[bytes] = None
            if img_meta.path is not None and img_meta.path.exists():
                try:
                    data = await asyncio.get_running_loop().run_in_executor(None, img_meta.path.read_bytes)
                except OSError as exc:
                    log.warning("AutoLogger: failed to read tmp image for message %s: %s", entry.message_id, exc)

            # Live fallback if file was missing
            if not data:
                data = await self._fetch_fallback_bytes(img_meta)

            if data:
                files.append(discord.File(io.BytesIO(data), filename=img_meta.filename))

        embed = self._build_embed(
            title="Message Deleted",
            color=DELETE_COLOR,
            entry=entry,
            before=entry.content,
        )
        if files:
            embed.set_image(url=f"attachment://{files[0].filename}")
        elif entry.images:
            embed.set_image(url=entry.images[0].proxy_url or entry.images[0].url)

        jump_url = f"https://discord.com/channels/{entry.guild_id}/{entry.channel_id}/{entry.message_id}"
        view = MessageLogView(user_id=entry.author_id, jump_url=jump_url, is_edit=False)

        try:
            await self._send(embed, files=files, view=view)
        finally:
            self._discard_entry(entry)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        for message_id in payload.message_ids:
            entry = self._cache.pop(message_id)
            if entry is not None:
                self._discard_entry(entry)

    # ---- member joins / leaves -------------------------------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not self._is_log_guild(member.guild.id):
            return

        embed = self._build_member_embed(
            title="Member Joined",
            color=JOIN_COLOR,
            user=member,
            mention=f"<@{member.id}>",
        )
        age = format_age(discord.utils.utcnow() - member.created_at)
        embed.add_field(name="Account Age", value=age, inline=False)
        await self._send(embed)

    @commands.Cog.listener()
    async def on_raw_member_remove(self, payload: discord.RawMemberRemoveEvent) -> None:
        if not self._is_log_guild(payload.guild_id):
            return

        user = payload.user
        await self._send(
            self._build_member_embed(
                title="Member Left",
                color=LEAVE_COLOR,
                user=user,
                mention=f"<@!{user.id}>",
            )
        )

    # ---- role given / role removed (Dyno style) --------------------------

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if not self._is_log_guild(after.guild.id):
            return

        if before.roles == after.roles:
            return

        before_set = set(before.roles)
        after_set = set(after.roles)

        added_roles = [r for r in after.roles if r not in before_set and not r.is_default()]
        removed_roles = [r for r in before.roles if r not in after_set and not r.is_default()]

        avatar_url = after.display_avatar.url

        if added_roles:
            label = "role" if len(added_roles) == 1 else "roles"
            roles_str = " , ".join(f"`{r.name}`" for r in added_roles)
            embed = discord.Embed(
                description=f"<@{after.id}> **was given the {label}** {roles_str}",
                colour=EDIT_COLOR,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_author(name=after.name, icon_url=avatar_url)
            embed.set_footer(text=f"ID: {after.id}")
            await self._send(embed)

        if removed_roles:
            label = "role" if len(removed_roles) == 1 else "roles"
            roles_str = " , ".join(f"`{r.name}`" for r in removed_roles)
            embed = discord.Embed(
                description=f"<@{after.id}> **was removed from the {label}** {roles_str}",
                colour=LEAVE_COLOR,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_author(name=after.name, icon_url=avatar_url)
            embed.set_footer(text=f"ID: {after.id}")
            await self._send(embed)

    # ---- channel created / deleted / updated (Dyno style) ----------------

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if not self._is_log_guild(channel.guild.id):
            return

        ch_type = format_channel_type(channel)
        lines = [
            f"**{ch_type} Created: #{channel.name}**",
            f"**Channel:** <#{channel.id}>",
        ]
        if getattr(channel, "category", None):
            lines.append(f"**Category:** {channel.category.name}")

        embed = discord.Embed(
            description="\n".join(lines),
            colour=JOIN_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        icon_url = channel.guild.icon.url if channel.guild.icon else None
        embed.set_author(name=channel.guild.name, icon_url=icon_url)
        embed.set_footer(text=f"ID: {channel.id}")
        await self._send(embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if not self._is_log_guild(channel.guild.id):
            return

        ch_type = format_channel_type(channel)
        lines = [f"**{ch_type} Deleted: #{channel.name}**"]
        if getattr(channel, "category", None):
            lines.append(f"**Category:** {channel.category.name}")

        embed = discord.Embed(
            description="\n".join(lines),
            colour=LEAVE_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        icon_url = channel.guild.icon.url if channel.guild.icon else None
        embed.set_author(name=channel.guild.name, icon_url=icon_url)
        embed.set_footer(text=f"ID: {channel.id}")
        await self._send(embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        if not self._is_log_guild(after.guild.id) or after.id in IGNORED_CHANNEL_IDS:
            return

        changes: List[tuple[str, str]] = []

        if before.name != after.name:
            changes.append(("Name Changed", f"**Before:** #{before.name}\n**After:** #{after.name}"))

        if getattr(before, "topic", None) != getattr(after, "topic", None):
            b_topic = truncate(getattr(before, "topic", None) or "*(none)*", 400)
            a_topic = truncate(getattr(after, "topic", None) or "*(none)*", 400)
            changes.append(("Topic Changed", f"**Before:** {b_topic}\n**After:** {a_topic}"))

        if getattr(before, "slowmode_delay", None) != getattr(after, "slowmode_delay", None):
            b_sm = getattr(before, "slowmode_delay", 0)
            a_sm = getattr(after, "slowmode_delay", 0)
            changes.append(("Slowmode Changed", f"**Before:** `{b_sm}s`\n**After:** `{a_sm}s`"))

        if getattr(before, "nsfw", None) != getattr(after, "nsfw", None):
            changes.append(("NSFW Changed", f"**Before:** `{before.nsfw}`\n**After:** `{after.nsfw}`"))

        if getattr(before, "category", None) != getattr(after, "category", None):
            b_cat = before.category.name if getattr(before, "category", None) else "*(none)*"
            a_cat = after.category.name if getattr(after, "category", None) else "*(none)*"
            changes.append(("Category Changed", f"**Before:** {b_cat}\n**After:** {a_cat}"))

        if not changes:
            return

        ch_type = format_channel_type(after)
        embed = discord.Embed(
            description=f"**{ch_type} Updated: <#{after.id}> (`#{after.name}`)**",
            colour=EDIT_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        for field_name, field_val in changes:
            embed.add_field(name=field_name, value=field_val, inline=False)

        icon_url = after.guild.icon.url if after.guild.icon else None
        embed.set_author(name=after.guild.name, icon_url=icon_url)
        embed.set_footer(text=f"ID: {after.id}")
        await self._send(embed)

    # ---- embed builders (Dyno-style layout) ------------------------------

    @staticmethod
    def _build_embed(
        *,
        title: str,
        color: discord.Colour,
        entry: CachedMessage,
        before: str,
        after: Optional[str] = None,
    ) -> discord.Embed:
        header = f"From: <@{entry.author_id}>   In: <#{entry.channel_id}>"
        timestamp = f"<t:{int(time.time())}:f>"
        meta = f"-# Author: {entry.author_id} | Message ID: {entry.message_id}\n-# {timestamp}"

        if after is not None:
            parts = [
                header,
                "",
                f"**Before**\n{truncate(before)}",
                "",
                f"**After**\n{truncate(after)}",
                "",
                meta,
            ]
        else:
            body = truncate(before) if before else "*(image / attachment)*"
            parts = [header, "", body, "", meta]

        return discord.Embed(
            title=title,
            description="\n".join(parts),
            colour=color,
        )

    @staticmethod
    def _build_member_embed(
        *,
        title: str,
        color: discord.Colour,
        user: discord.abc.User,
        mention: str,
    ) -> discord.Embed:
        avatar_url = user.display_avatar.url
        embed = discord.Embed(
            description=f"{mention} {discord.utils.escape_markdown(user.name)}",
            colour=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=title, icon_url=avatar_url)
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"ID: {user.id}")
        return embed

    # ---- delivery --------------------------------------------------------

    async def _resolve_log_channel(self) -> Optional[discord.abc.Messageable]:
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(LOG_CHANNEL_ID)
            except discord.DiscordException:
                channel = None

        if channel is None or not hasattr(channel, "send"):
            if not self._warned_missing_channel:
                self._warned_missing_channel = True
                log.warning(
                    "AutoLogger: log channel %s is not a text channel the bot can see; dropping logs.",
                    LOG_CHANNEL_ID,
                )
            return None
        return channel  # type: ignore[return-value]

    async def _send(
        self,
        embed: discord.Embed,
        file: Optional[discord.File] = None,
        files: Optional[List[discord.File]] = None,
        view: Optional[discord.ui.View] = None,
    ) -> None:
        channel = await self._resolve_log_channel()
        if channel is None:
            return

        kwargs: dict = {
            "embed": embed,
            "allowed_mentions": discord.AllowedMentions.none(),
        }
        if files:
            kwargs["files"] = files
        elif file is not None:
            kwargs["file"] = file
        if view is not None:
            kwargs["view"] = view

        try:
            await channel.send(**kwargs)
        except discord.Forbidden:
            log.error("AutoLogger: missing permissions to post in log channel %s.", LOG_CHANNEL_ID)
        except discord.HTTPException as exc:
            log.error("AutoLogger: failed to post log: %s", exc)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoLogger(bot))
