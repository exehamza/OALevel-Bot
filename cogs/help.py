import discord
from discord.ext import commands
from config import Config

class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", aliases=["commands", "menu"], help="Displays available commands or specific command guidelines.")
    async def help(self, ctx, category_or_command: str = None):
        embed_color = getattr(Config, "EMBED_COLOR", 0x3498db)
        prefix = getattr(Config, "PREFIX", "$")

        # Define detailed guides for your core moderation/utility commands
        command_guides = {
            "purge": {
                "description": "Purges a set number of messages from the current text channel.",
                "usage": f"`{prefix}purge <amount>`",
                "example": f"`{prefix}purge 50`",
                "notes": "• Maximum amount allowed at once is 100 messages.\n• Messages older than 14 days cannot be bulk purged due to Discord API limits."
            },
            "kick": {
                "description": "Kicks a member from the server and direct messages them the reason.",
                "usage": f"`{prefix}kick <@member/ID> [reason]`",
                "example": f"`{prefix}kick @User123 Breaking chat rules`",
                "notes": "• You cannot kick users with a higher or equal administrative role to yours."
            },
            "ban": {
                "description": "Permanently bans a member from the server and direct messages them the reason.",
                "usage": f"`{prefix}ban <@member/ID> [reason]`",
                "example": f"`{prefix}ban @User123 Severe raiding behaviors`",
                "notes": "• Clears the user's message history and restricts them from re-joining."
            },
            "unban": {
                "description": "Revokes a ban layout for a user using their exact ID or username tag.",
                "usage": f"`{prefix}unban <username#desc / UserID>`",
                "example": f"`{prefix}unban 123456789012345678`",
                "notes": "• Scans the audit ban registry log to locate the matching entity."
            },
            "mute": {
                "description": "Mutes a server member using Discord's native isolated timeout system.",
                "usage": f"`{prefix}mute <@member/ID> <duration> [reason]`",
                "example": f"`{prefix}mute @User123 2h Continued disruption`",
                "notes": "• Durations accept explicit flags: `m` (minutes), `h` (hours), `d` (days).\n• Maximum cap configuration is 28 days (`28d`)."
            },
            "unmute": {
                "description": "Instantly lifts an active timeout restriction from a server member.",
                "usage": f"`{prefix}unmute <@member/ID> [reason]`",
                "example": f"`{prefix}unmute @User123 Appeal processed successfully`",
                "notes": "• Restores immediate chat and voice access privileges."
            },
            "say": {
                "description": "Forces the bot to mirror and broadcast an explicit text string.",
                "usage": f"`{prefix}say <message>`",
                "example": f"`{prefix}say Regular server maintenance tonight at 8 PM.`",
                "notes": "• Deletes the administrator's original call string to keep operations clean."
            },
            "reply": {
                "description": "Forces the bot to execute a target-threaded reply to a specific message ID.",
                "usage": f"`{prefix}reply <message_id> <message>`",
                "example": f"`{prefix}reply 1234567890123456 Hello, this is an official staff follow-up.`",
                "notes": "• The target message must exist inside the same text channel where this command is run."
            },
            "snipe": {
                "description": "Recovers up to the last 5 deleted messages in the current channel.",
                "usage": f"`{prefix}snipe [index 1-5]`",
                "example": f"`{prefix}snipe 1`",
                "notes": "• Defaults to `1` (the most recently deleted message) if an index isn't provided."
            },
            "steal": {
                "description": "Steals a custom emoji or a replied sticker and adds it directly to this server.",
                "usage": f"`{prefix}steal <emoji> [custom_name]`",
                "example": f"`{prefix}steal :cool_emoji: global_cool`",
                "notes": "• You can also use this by replying to a message containing a sticker with just `{prefix}steal`."
            },
            "close": {
                "description": "Safely closes, archives, and locks an active staff modmail thread.",
                "usage": f"`{prefix}close`",
                "example": f"`{prefix}close`",
                "notes": "• Can only be executed inside a valid thread channel under the designated Modmail channel category."
            }
        }

        # CASE 1: USER IS ASKING FOR A SPECIFIC COMMAND GUIDE
        if category_or_command:
            command_name = category_or_command.strip().lower().replace(prefix, "")
            
            guide_embed = discord.Embed(color=embed_color, timestamp=discord.utils.utcnow())
            guide_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)

            # Check if we have an explicit detailed guide written above
            if command_name in command_guides:
                guide = command_guides[command_name]
                guide_embed.title = f"Command Guide: {prefix}{command_name}"
                guide_embed.description = guide["description"]
                guide_embed.add_field(name="System Syntax", value=guide["usage"], inline=False)
                guide_embed.add_field(name="Execution Example", value=guide["example"], inline=False)
                guide_embed.add_field(name="Operational Notes", value=guide["notes"], inline=False)
                return await ctx.send(embed=guide_embed)
            
            # FALLBACK CASE: The command exists on the bot, but doesn't have an explicit manual entry
            else:
                actual_command = self.bot.get_command(command_name)
                if actual_command:
                    # Treat cases like $rank where it prints its mapped card assignment
                    desc = actual_command.help or f"Shows your {command_name} card details or statistical breakdowns."
                    guide_embed.title = f"Command Information: {prefix}{command_name}"
                    guide_embed.description = f"The `{prefix}{command_name}` command {desc.lower()}"
                    guide_embed.add_field(name="system Syntax", value=f"`{prefix}{command_name}`", inline=False)
                    return await ctx.send(embed=guide_embed)
                else:
                    # The command doesn't exist on the bot at all
                    return await ctx.send(f"Command `{prefix}{command_name}` does not exist.", delete_after=5)

        # CASE 2: MAIN HELP MENU (Displays if no specific command parameter is passed)
        embed = discord.Embed(
            title="O/A Level Community Assistant | Command Menu",
            description=(
                f"Welcome! Use `{prefix}help <command>` to fetch deeper syntax configurations.\n"
                f"**Current Prefix:** `{prefix}`\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=embed_color
        )

        # 1. MODERATION
        embed.add_field(
            name="Moderation Module",
            value=(
                f"`{prefix}purge` ➔ Clean up specific chat histories.\n"
                f"`{prefix}kick` ➔ Remove a member safely from the guild.\n"
                f"`{prefix}ban` / `{prefix}unban` ➔ Manage severe access revocations.\n"
                f"`{prefix}mute` / `{prefix}unmute` ➔ Manage native server timeouts.\n"
                f"`{prefix}say` / `{prefix}reply` ➔ Broadcast messages or inline responses."
            ),
            inline=False
        )

        # 2. LOGS & UTILITY
        embed.add_field(
            name="Logs & Utility Tools",
            value=(
                f"`{prefix}snipe <1-5>` ➔ Recover up to the last 5 deleted messages.\n"
                f"`{prefix}steal` ➔ Extract a custom emoji or a sticker asset into your server."
            ),
            inline=False
        )

        # 3. MODMAIL & AUTO MOD
        embed.add_field(
            name="Modmail & AutoMod Infrastructure",
            value=(
                f"`{prefix}close` ➔ Safe termination and archive processing for a staff thread.\n"
                f"`{prefix}automod` ➔ Comprehensive keyword configuration blueprints.\n"
                f"`{prefix}keyword` ➔ Dynamic internal system administration guide."
            ),
            inline=False
        )

        # 4. LEVELING & LOCK-IN
        embed.add_field(
            name="Engagement & System Access",
            value=(
                f"`{prefix}level` ➔ Review current experience point tierings.\n"
                f"`{prefix}leaderboard` ➔ Display server engagement positioning charts.\n"
                f"`{prefix}lockin` ➔ Execute focus constraints."
            ),
            inline=False
        )

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(
            text=f"Requested by {ctx.author.name} • Total Commands: 16", 
            icon_url=ctx.author.display_avatar.url
        )
        embed.timestamp = discord.utils.utcnow()

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCommand(bot))