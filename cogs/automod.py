import json
import os
import re

import discord
from discord.ext import commands

from config import Config


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.blocked_words = set()
        self.load_blocked_words()

    def load_blocked_words(self):
        os.makedirs(os.path.dirname(Config.BLOCKED_WORDS_FILE), exist_ok=True)

        if not os.path.exists(Config.BLOCKED_WORDS_FILE):
            self.save_blocked_words()
            return

        try:
            with open(Config.BLOCKED_WORDS_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            data = {}

        if isinstance(data, dict):
            words = data.get("blocked_words", [])
        elif isinstance(data, list):
            words = data
        else:
            words = []

        self.blocked_words = {
            str(word).strip().lower()
            for word in words
            if str(word).strip()
        }

    def save_blocked_words(self):
        os.makedirs(os.path.dirname(Config.BLOCKED_WORDS_FILE), exist_ok=True)
        with open(Config.BLOCKED_WORDS_FILE, "w", encoding="utf-8") as file:
            json.dump(
                {"blocked_words": sorted(self.blocked_words)},
                file,
                indent=2,
                ensure_ascii=False,
            )
            file.write("\n")

    def contains_swear_word(self, content):
        for word in self.blocked_words:
            pattern = rf"(?<!\w){re.escape(word)}(?!\w)"
            if re.search(pattern, content, flags=re.IGNORECASE):
                return True
        return False

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"AutoMod loaded with {len(self.blocked_words)} blocked words.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return

        if message.author.guild_permissions.manage_messages:
            return

        if self.contains_swear_word(message.content):
            try:
                await message.delete()
            except discord.Forbidden:
                return

            await message.channel.send(
                f"{message.author.mention}, that word is not allowed here."
            )

    @commands.group(name="automod", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx):
        await ctx.send(f"Use `{Config.PREFIX}automod add <word>` to add a blocked word.")

    @automod.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def add_swear_word(self, ctx, *, word: str):
        word = word.strip().lower()

        if not word:
            return await ctx.send("Please provide a word to block.")

        if word in self.blocked_words:
            return await ctx.send(f"`{word}` is already in the AutoMod list.")

        self.blocked_words.add(word)
        self.save_blocked_words()

        await ctx.send(f"Added `{word}` to the AutoMod blocked word list.")

    @automod.error
    @add_swear_word.error
    async def automod_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need the Manage Server permission to change AutoMod settings.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing word. Use `{Config.PREFIX}automod add <word>`.")
        else:
            raise error


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
