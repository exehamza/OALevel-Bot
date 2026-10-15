"""
AutoLogger - Dyno-style message edit/delete and member join/leave logger for discord.py.

Drop this file into your bot's ``cogs/`` folder and load it with:

    await bot.load_extension("cogs.autologger")

Requirements
------------
* discord.py >= 2.0
* Intents: ``message_content`` and ``members`` (both privileged - enable them in
  the Developer Portal) on top of the default intents, e.g.:

      intents = discord.Intents.default()
      intents.message_content = True
      intents.members = True

* Bot permissions in the log channel: View Channel, Send Messages,
  Embed Links, Attach Files.
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
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Awaitable, Callable, Optional, Set

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

LOG_CHANNEL_ID = 1296530025637740554
IGNORED_CHANNEL_IDS = {LOG_CHANNEL_ID, 1324373003680743503}

DELETE_COLOR = discord.Colour(0xED4245)  # red
EDIT_COLOR = discord.Colour(0x3880D4)  # blue
JOIN_COLOR = discord.Colour(0x43B581)  # green
LEAVE_COLOR = discord.Colour(0xFF4500)  # orange-red

CACHE_MAX_ENTRIES = 1000
SEGMENT_MAX = 1024  # per-segment cap (before/after) - keeps the description well under 4096

# Images are downloaded when the message is sent so they can be re-uploaded
# if the message is deleted (the CDN link may not survive the deletion).
# Keep this under your server's upload limit (10 MB is the safe default).
MAX_IMAGE_DOWNLOAD_BYTES = 8 * 1024 * 1024
IMAGE_TMP_DIR = Path(tempfile.gettempdir()) / "autologger-images"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

IGNORE_BOTS = True

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def truncate(value: str, limit: int = SEGMENT_MAX) -> str:
    if not value:
        return "*(empty)*"
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def format_age(delta: timedelta) -> str:
    """Human-readable duration using the two largest non-zero units,
    e.g. ``14 mins, 43 secs`` or ``3 years, 2 months``."""
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
            if len(parts) == 2:
                break
    return ", ".join(parts) or "0 secs"


def remove_file(path: Optional[Path]) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.debug("AutoLogger: could not remove tmp file %s: %s", path, exc)


@dataclass
class CachedMessage:
    message_id: int
    channel_id: int
    channel_name: str
    guild_id: int
    author_id: int
    author_name: str
    content: str
    image_url: Optional[str] = None
    image_filename: Optional[str] = None
    image_path: Optional[Path] = None


class MessageCache:
    """Tiny in-memory LRU cache built on OrderedDict."""

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
        """Look up an entry without refreshing its recency."""
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
        """Remove and return an entry. The caller owns any cleanup."""
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
    """Logs message edits and deletions to a single channel, Dyno-style.

    Uses the raw gateway events with its own cache as the source of truth, so
    it keeps working for messages that have dropped out of discord.py's
    internal message cache.
    """

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

    # ---- caching ---------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not self._should_track(message):
            return

        image = self._first_image(message)
        entry = CachedMessage(
            message_id=message.id,
            channel_id=message.channel.id,
            channel_name=getattr(message.channel, "name", None) or str(message.channel.id),
            guild_id=message.guild.id,  # type: ignore[union-attr]
            author_id=message.author.id,
            author_name=message.author.name,
            content=message.content,
            image_url=image.url if image else None,
        )
        self._cache.set(message.id, entry)

        if image is not None and 0 < image.size <= MAX_IMAGE_DOWNLOAD_BYTES:
            self._spawn(self._download_image(entry, image))

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
        """If the log channel lives in a specific server, only log that server."""
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        log_guild = getattr(log_channel, "guild", None)
        return log_guild is None or log_guild.id == guild_id

    @staticmethod
    def _first_image(message: discord.Message) -> Optional[discord.Attachment]:
        for attachment in message.attachments:
            if (attachment.content_type or "").startswith("image/"):
                return attachment
            if attachment.filename.lower().endswith(IMAGE_EXTENSIONS):
                return attachment
        return None

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _download_image(self, entry: CachedMessage, attachment: discord.Attachment) -> None:
        try:
            data = await attachment.read()
        except discord.DiscordException as exc:
            log.warning("AutoLogger: failed to pre-fetch image for message %s: %s", entry.message_id, exc)
            return
        if len(data) > MAX_IMAGE_DOWNLOAD_BYTES:
            return

        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", attachment.filename)
        dest = IMAGE_TMP_DIR / f"{entry.message_id}-{safe_name}"
        try:
            IMAGE_TMP_DIR.mkdir(parents=True, exist_ok=True)
            await asyncio.get_running_loop().run_in_executor(None, dest.write_bytes, data)
        except OSError as exc:
            log.warning("AutoLogger: failed to write tmp image for message %s: %s", entry.message_id, exc)
            return

        # The message may have been deleted/evicted while we were downloading.
        if self._cache.peek(entry.message_id) is entry:
            entry.image_path = dest
            entry.image_filename = safe_name
        else:
            remove_file(dest)

    @staticmethod
    def _discard_entry(entry: CachedMessage) -> None:
        remove_file(entry.image_path)

    # ---- edits -----------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.guild_id is None or payload.channel_id in IGNORED_CHANNEL_IDS:
            return

        # Updates that don't touch the text (link embeds loading, pins, ...)
        # either omit "content" or leave it unchanged.
        after = payload.data.get("content")
        if after is None:
            return

        entry = self._cache.get(payload.message_id)
        if entry is None:
            return

        before = entry.content
        if before == after:
            return

        # Refresh the cache so a second edit still has an accurate "before".
        entry.content = after

        await self._send(
            self._build_embed(
                title="Message Edited",
                color=EDIT_COLOR,
                entry=entry,
                before=before,
                after=after,
            )
        )

    # ---- deletes ---------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id is None or payload.channel_id in IGNORED_CHANNEL_IDS:
            return

        entry = self._cache.pop(payload.message_id)
        if entry is None:
            return

        file: Optional[discord.File] = None
        if entry.image_path is not None:
            try:
                data = await asyncio.get_running_loop().run_in_executor(None, entry.image_path.read_bytes)
                file = discord.File(
                    io.BytesIO(data),
                    filename=entry.image_filename or entry.image_path.name,
                )
            except OSError as exc:
                log.warning("AutoLogger: failed to read tmp image for message %s: %s", entry.message_id, exc)

        embed = self._build_embed(
            title="Message Deleted",
            color=DELETE_COLOR,
            entry=entry,
            before=entry.content,
        )
        if file is not None:
            embed.set_image(url=f"attachment://{file.filename}")
        elif entry.image_url:
            embed.set_image(url=entry.image_url)

        try:
            await self._send(embed, file)
        finally:
            remove_file(entry.image_path)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        # Not logged individually (a purge would flood the log channel), but
        # purge the cache so tmp images don't linger.
        for message_id in payload.message_ids:
            entry = self._cache.pop(message_id)
            if entry is not None:
                remove_file(entry.image_path)

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
        # Raw event: fires even when the member isn't in discord.py's cache.
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

    # ---- embed builder (Dyno-style layout) -------------------------------

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

        meta_line = (
            f"-# Author: {discord.utils.escape_markdown(entry.author_name)} "
            f"(`{entry.author_id}`) | Message ID: `{entry.message_id}`"
        )
        # Jump link only makes sense while the message still exists (edits).
        if after is not None:
            url = f"https://discord.com/channels/{entry.guild_id}/{entry.channel_id}/{entry.message_id}"
            meta_line += f" | [🔗 Jump to Message]({url})"
        meta = f"{meta_line}\n-# {timestamp}"

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
            parts = [header, "", truncate(before), "", meta]

        return discord.Embed(
            title=title,
            description="\n".join(parts),
            colour=color,
            timestamp=discord.utils.utcnow(),
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

    async def _send(self, embed: discord.Embed, file: Optional[discord.File] = None) -> None:
        channel = await self._resolve_log_channel()
        if channel is None:
            return
        try:
            await channel.send(
                embed=embed,
                file=file,  # type: ignore[arg-type]
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            log.error("AutoLogger: missing permissions to post in log channel %s.", LOG_CHANNEL_ID)
        except discord.HTTPException as exc:
            log.error("AutoLogger: failed to post log: %s", exc)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoLogger(bot))
