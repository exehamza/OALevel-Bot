import json
import os
import re
import datetime
import discord
from discord.ext import commands
from config import Config


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.blocked_words = set()
        self.whitelisted_users = set()  # Tracks user IDs exempt from AutoMod
        
        # New dictionary to track violation timestamps: {user_id: [datetime, datetime...]}
        self.infractions = {} 
        
        self.load_automod_data()

    def load_automod_data(self):
        """Loads blocked words and whitelisted users from the configuration file."""
        os.makedirs(os.path.dirname(Config.BLOCKED_WORDS_FILE), exist_ok=True)

        if not os.path.exists(Config.BLOCKED_WORDS_FILE):
            self.save_automod_data()
            return

        try:
            with open(Config.BLOCKED_WORDS_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            data = {}

        # Parse blocked words safely
        if isinstance(data, dict):
            words = data.get("blocked_words", [])
            whitelist = data.get("whitelisted_users", [])
        else:
            words = []
            whitelist = []

        self.blocked_words = {
            str(word).strip().lower()
            for word in words
            if str(word).strip()
        }

        # Parse user IDs safely as integers
        self.whitelisted_users = {
            int(user_id)
            for user_id in whitelist
        }

    def save_automod_data(self):
        """Saves current blocked words and whitelisted users back to the file."""
        os.makedirs(os.path.dirname(Config.BLOCKED_WORDS_FILE), exist_ok=True)
        with open(Config.BLOCKED_WORDS_FILE, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "blocked_words": sorted(self.blocked_words),
                    "whitelisted_users": sorted(self.whitelisted_users)
                },
                file,
                indent=2,
                ensure_ascii=False,
                )
            file.write("\n")

    def contains_swear_word(self, content):
        """Checks if a string contains any of the exact blacklisted phrases."""
        for word in self.blocked_words:
            pattern = rf"(?<!\w){re.escape(word)}(?!\w)"
            if re.search(pattern, content, flags=re.IGNORECASE):
                return True
        return False

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"AutoMod loaded with {len(self.blocked_words)} blocked words and {len(self.whitelisted_users)} whitelisted users.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return

        # Bypass check if the user is whitelisted
        if message.author.id in self.whitelisted_users:
            return

        # Bypass check if user has message management permissions
        if message.author.guild_permissions.manage_messages:
            return

        if self.contains_swear_word(message.content):
            try:
                await message.delete()
            except discord.Forbidden:
                return

            # --- VIOLATION TRACKING LOGIC ---
            now = datetime.datetime.utcnow()
            user_id = message.author.id

            if user_id not in self.infractions:
                self.infractions[user_id] = []

            # 1. Clear out violation records older than 2 minutes (rolling window)
            self.infractions[user_id] = [
                timestamp for timestamp in self.infractions[user_id]
                if now - timestamp < datetime.timedelta(minutes=2)
            ]

            # 2. Add current violation timestamp
            self.infractions[user_id].append(now)

            # 3. Check if violations hit 5 within the timeframe
            if len(self.infractions[user_id]) >= 5:
                # Clear tracking list for this user so it restarts clean after timeout
                self.infractions[user_id] = []
                
                try:
                    # Apply a 30-minute native Discord timeout
                    await message.author.timeout(datetime.timedelta(minutes=30), reason="AutoMod: Exceeded word filter limits.")
                    
                    mute_embed = discord.Embed(
                        description=f"🚫 {message.author.mention} **has been muted for 30 minutes for repeating blacklisted language.**",
                        color=discord.Color.red()
                    )
                    return await message.channel.send(embed=mute_embed)
                except discord.Forbidden:
                    # In case the bot lacks role hierarchy power over the targeted member
                    pass

            # Fallback normal message warning if under 5 violations
            warn_embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> {message.author.mention}, **that word is not allowed here.** ({len(self.infractions[user_id])}/5)",
                color=discord.Color.red()
            )
            await message.channel.send(embed=warn_embed, delete_after=10)

    @commands.group(name="automod", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx):
        """Root command instruction guide."""
        embed = discord.Embed(
            title="🛡️ AutoMod Configuration Help",
            description="Manage your server filter dynamically using the subcommands below.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Add Word", value=f"`{Config.PREFIX}automod add <word>`", inline=True)
        embed.add_field(name="Remove Word", value=f"`{Config.PREFIX}automod remove <word>`", inline=True)
        embed.add_field(name="View Words", value=f"`{Config.PREFIX}automod view`", inline=True)
        embed.add_field(name="Whitelist User", value=f"`{Config.PREFIX}automod whitelist @user`", inline=False)
        await ctx.send(embed=embed)

    @automod.command(name="add")
    @commands.has_permissions(manage_guild=True)
    async def add_swear_word(self, ctx, *, word: str):
        """Adds a single word to the filter list."""
        word = word.strip().lower()

        if not word:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Please provide a word to block.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if word in self.blocked_words:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> `{word}` **is already in the AutoMod list.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        self.blocked_words.add(word)
        self.save_automod_data()
        
        embed = discord.Embed(
            description=f"✅ **Added** `{word}` **to the AutoMod blocked word list.**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @automod.command(name="remove", aliases=["delete"])
    @commands.has_permissions(manage_guild=True)
    async def remove_swear_word(self, ctx, *, word: str):
        """Removes a word from the filter list."""
        word = word.strip().lower()

        if word not in self.blocked_words:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> `{word}` **is not currently in the AutoMod list.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        self.blocked_words.remove(word)
        self.save_automod_data()
        
        embed = discord.Embed(
            description=f"✅ **Removed** `{word}` **from the AutoMod blocked word list.**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @automod.command(name="view", aliases=["list"])
    @commands.has_permissions(manage_guild=True)
    async def view_swear_words(self, ctx):
        """Displays all words currently active on the block filter."""
        if not self.blocked_words:
            embed = discord.Embed(
                description="🛡️ **The AutoMod blocked words list is currently empty.**",
                color=discord.Color.blue()
            )
            return await ctx.send(embed=embed)

        sorted_words = sorted(self.blocked_words)
        words_string = ", ".join(f"`{word}`" for word in sorted_words)

        if len(words_string) > 1900:
            with open("blocked_words_export.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(sorted_words))
            
            embed = discord.Embed(
                description="📁 **The blocked words list is too long to display. Exporting to a file below:**",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed, file=discord.File("blocked_words_export.txt"))

        embed = discord.Embed(
            title="🚫 Current AutoMod Blocked Words",
            description=words_string,
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Total blacklisted words: {len(self.blocked_words)}")
        await ctx.send(embed=embed)

    @automod.command(name="whitelist")
    @commands.has_permissions(manage_guild=True)
    async def whitelist_user(self, ctx, member: discord.Member):
        """Toggles immunity status for a user explicitly."""
        if member.bot:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Bots are already bypassed automatically by AutoMod.**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if member.id in self.whitelisted_users:
            self.whitelisted_users.remove(member.id)
            self.save_automod_data()
            embed = discord.Embed(
                description=f"**Removed** {member.mention} **from the whitelist.** They are now subject to the chat filter.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        else:
            self.whitelisted_users.add(member.id)
            self.save_automod_data()
            embed = discord.Embed(
                description=f"**Added** {member.mention} **to the whitelist.** They can now say blocked words safely.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)

    @automod.error
    @add_swear_word.error
    @remove_swear_word.error
    @view_swear_words.error
    @whitelist_user.error
    async def automod_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **You need the Manage Server permission to change AutoMod settings.**",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> **Missing arguments.** Run `{Config.PREFIX}automod` to see syntax rules.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> **Could not find that member.** Please make sure to explicitly mention them.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            raise error


async def setup(bot):
    await bot.add_cog(AutoMod(bot))