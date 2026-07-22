import discord
from discord.ext import commands

# Define permission hierarchy levels
PERM_MEMBER = 0
PERM_MOD = 1
PERM_ADMIN = 2

# Central Data Repository
# Format for each command:
# "command_name": {
#     "category": "Category Name",
#     "level": PERM_LEVEL,
#     "aliases": ["alias1", "alias2"],
#     "usage": "<required_arg> [optional_arg]",
#     "desc": "Short, active-voice ASD-STE100 description."
# }
COMMAND_DATA = {
    # --- AUTOMESSAGE ---
    "automessagesetup": {
        "category": "Auto Message",
        "level": PERM_MOD,
        "aliases": ["amsetup"],
        "usage": "<time_interval> <session>",
        "desc": "Sets automatic messages for a channel."
    },
    "automessagestop": {
        "category": "Auto Message",
        "level": PERM_MOD,
        "aliases": ["amstop"],
        "usage": "",
        "desc": "Stops automatic messages for a channel."
    },

    # --- AUTOMOD ---
    "automod": {
        "category": "Auto Mod",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "",
        "desc": "Shows auto moderation settings."
    },
    "automod add": {
        "category": "Auto Mod",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<word>",
        "desc": "Adds a word to the bad words list."
    },
    "automod remove": {
        "category": "Auto Mod",
        "level": PERM_ADMIN,
        "aliases": ["delete"],
        "usage": "<word>",
        "desc": "Removes a word from the bad words list."
    },
    "automod view": {
        "category": "Auto Mod",
        "level": PERM_ADMIN,
        "aliases": ["list"],
        "usage": "",
        "desc": "Shows all blocked words."
    },
    "automod whitelist": {
        "category": "Auto Mod",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member>",
        "desc": "Allows a user to bypass auto moderation."
    },

    # --- AVATAR ---
    "avatar": {
        "category": "Avatar",
        "level": PERM_MEMBER,
        "aliases": ["av", "pfp"],
        "usage": "[@member]",
        "desc": "Shows the profile picture of a user."
    },

    # --- COLOR ROLE ---
    "colour": {
        "category": "Color Role",
        "level": PERM_MEMBER,
        "aliases": ["color"],
        "usage": "",
        "desc": "Opens the color selection menu."
    },

    # --- ECONOMY: GENERAL ---
    "balance": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["bal"],
        "usage": "[@member]",
        "desc": "Shows the current node balance of a member."
    },
    "daily": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Claims daily node reward."
    },
    "monthly": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Claims monthly node reward."
    },
    "richest": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Shows top members by node balance."
    },
    "transactions": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["tx"],
        "usage": "",
        "desc": "Shows personal node transaction history."
    },
    "give": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["transfer", "send"],
        "usage": "<@member> <amount>",
        "desc": "Transfers nodes to another member."
    },

    # --- ECONOMY: ADMIN ---
    "addnodes": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Adds nodes to a member account."
    },
    "removenodes": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Removes nodes from a member account."
    },
    "setnodes": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Sets the node balance for a member."
    },
    "economyreset": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member>",
        "desc": "Resets economy data for a member."
    },
    "economylog": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "[@member|user_id]",
        "desc": "Shows administrative economy transaction logs."
    },
    "economyblacklist add/remove": {
        "category": "Economy Management",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "[@member]",
        "desc": "Blacklists/Whitelists a member from using economy commands."
    },
    
    # --- GAMES ---
    "coinflip": {
        "category": "Games",
        "level": PERM_MEMBER,
        "aliases": ["cf"],
        "usage": "<bet>",
        "desc": "Flips a coin to double or lose the bet."
    },
    "slots": {
        "category": "Games",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<bet>",
        "desc": "Plays the slot machine with a node bet."
    },

    # --- KEYWORDS ---
    "keyword": {
        "category": "Keywords",
        "level": PERM_ADMIN,
        "aliases": ["keywords"],
        "usage": "",
        "desc": "Shows keyword trigger settings."
    },
    "keyword add": {
        "category": "Keywords",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<trigger> | <response>",
        "desc": "Adds an automatic keyword response."
    },
    "keyword remove": {
        "category": "Keywords",
        "level": PERM_ADMIN,
        "aliases": ["delete"],
        "usage": "<trigger>",
        "desc": "Deletes a keyword trigger."
    },
    "keyword view": {
        "category": "Keywords",
        "level": PERM_ADMIN,
        "aliases": ["list"],
        "usage": "",
        "desc": "Shows all saved keywords."
    },

    # --- LEVELS ---
    "level": {
        "category": "Levels",
        "level": PERM_MEMBER,
        "aliases": ["rank"],
        "usage": "[@member]",
        "desc": "Shows the current level and rank of a user."
    },
    "leaderboard": {
        "category": "Levels",
        "level": PERM_MEMBER,
        "aliases": ["lb"],
        "usage": "",
        "desc": "Shows top members by level."
    },
    "xp": {
        "category": "Levels",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "",
        "desc": "Shows XP management commands."
    },
    "xp add": {
        "category": "Levels",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Adds XP points to a member."
    },
    "xp remove": {
        "category": "Levels",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Removes XP points from a member."
    },

    # --- LOCKIN ---
    "lockin": {
        "category": "Lockin",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<time_input>",
        "desc": "Locks a channel for a set time."
    },

    # --- MODERATION ---
    "removecase": {
        "category": "Moderation",
        "level": PERM_ADMIN,
        "aliases": ["delcase", "deletecase"],
        "usage": "<case_id>",
        "desc": "Deletes a moderation case record."
    },
    "logs": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": ["history", "cases"],
        "usage": "<@member|user_id>",
        "desc": "Shows moderation history for a user."
    },
    "purge": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": ["clear"],
        "usage": "[@member] <amount>",
        "desc": "Deletes a specified number of messages."
    },
    "kick": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": [],
        "usage": "<@member> [reason]",
        "desc": "Removes a member from the server."
    },
    "ban": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": [],
        "usage": "<@member> [reason]",
        "desc": "Bans a member from the server."
    },
    "unban": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": [],
        "usage": "<username|ID>",
        "desc": "Removes a ban from a user."
    },
    "mute": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": ["timeout"],
        "usage": "<@member> <duration> [reason]",
        "desc": "Mutes a member for a duration."
    },
    "unmute": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": ["untimeout"],
        "usage": "<@member> [reason]",
        "desc": "Removes a mute from a member."
    },
    "warn": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": [],
        "usage": "<@member> [reason]",
        "desc": "Warns a member and records the event."
    },
    "say": {
        "category": "Moderation",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<message>",
        "desc": "Sends a message through the bot."
    },
    "reply": {
        "category": "Moderation",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "<channel> <message_id> <message>\n!reply <message_id> <message>",
        "desc": "Replies to a specific message ID and/or from a specific channel."
    },

    # --- NICKNAME ---
    "sn": {
        "category": "Nickname",
        "level": PERM_MOD,
        "aliases": [],
        "usage": "<@member> [nickname]",
        "desc": "Changes or resets a member nickname."
    },

    # --- RULES ---
    "rule": {
        "category": "Rules",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "[number]",
        "desc": "Displays server rules."
    },

    # --- SLOWMODE ---
    "slowmode": {
        "category": "Slowmode",
        "level": PERM_MOD,
        "aliases": ["sm"],
        "usage": "[duration]",
        "desc": "Sets channel message delay time."
    },

    # --- TRANSLATE ---
    "tr": {
        "category": "Translate",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<target_lang> (reply to message)",
        "desc": "Translates a message to another language."
    },
    "langs": {
        "category": "Translate",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Shows supported translation languages."
    },

    # --- UTILITY ---
    "ping": {
        "category": "Utility",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "[host]",
        "desc": "Checks bot latency or network host."
    },
    "steal": {
        "category": "Utility",
        "level": PERM_ADMIN,
        "aliases": [],
        "usage": "[emoji|sticker_reply]",
        "desc": "Adds an emoji or sticker to the server."
    }
}


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.remove_command("help")  # Unload default help command

    def get_user_level(self, ctx: commands.Context) -> int:
        """Determines the user's permission level based on permissions."""
        if not ctx.guild:
            return PERM_MEMBER
        
        perms = ctx.author.guild_permissions
        if perms.administrator:
            return PERM_ADMIN
        
        # Moderator checks
        if (
            perms.manage_messages or 
            perms.kick_members or 
            perms.ban_members or 
            perms.moderate_members or 
            perms.manage_nicknames or 
            perms.manage_guild
        ):
            return PERM_MOD
            
        return PERM_MEMBER

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context, *, query: str = None):
        """Displays filtered help commands or details for a specific command."""
        user_level = self.get_user_level(ctx)
        prefix = ctx.clean_prefix

        # --- CASE 1: SPECIFIC COMMAND HELP (!help <command>) ---
        if query:
            query = query.lower().strip()
            
            target_name = None
            target_info = None

            for name, data in COMMAND_DATA.items():
                if query == name or query in data.get("aliases", []):
                    target_name = name
                    target_info = data
                    break

            if not target_info or target_info["level"] > user_level:
                embed = discord.Embed(
                    title="Error",
                    description=f"Command `{query}` was not found or you do not have permission to view it.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

            embed = discord.Embed(
                title=f"Command: {prefix}{target_name}",
                description=target_info["desc"],
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Usage", 
                value=f"`{prefix}{target_name} {target_info['usage']}`".strip(), 
                inline=False
            )
            
            if target_info.get("aliases"):
                aliases_str = ", ".join([f"`{a}`" for a in target_info["aliases"]])
                embed.add_field(name="Aliases", value=aliases_str, inline=False)
                
            embed.add_field(name="Category", value=target_info["category"], inline=True)
            
            level_labels = {PERM_MEMBER: "Member", PERM_MOD: "Moderator", PERM_ADMIN: "Administrator"}
            embed.add_field(name="Required Role", value=level_labels.get(target_info["level"], "Member"), inline=True)
            
            await ctx.send(embed=embed)
            return

        # --- CASE 2: MAIN HELP MENU (!help) ---
        categories = {}
        for cmd_name, data in COMMAND_DATA.items():
            if data["level"] <= user_level:
                cat = data["category"]
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(cmd_name)

        embed = discord.Embed(
            title="Help Menu",
            color=discord.Color.blue()
        )

        if not categories:
            embed.description = "No commands available."
            await ctx.send(embed=embed)
            return

        # Build directory tree format
        tree_lines = ["Commands/                                                            "]
        sorted_cats = sorted(categories.keys())

        for c_idx, cat in enumerate(sorted_cats):
            is_last_cat = (c_idx == len(sorted_cats) - 1)
            cat_prefix = "└── " if is_last_cat else "├── "
            tree_lines.append(f"{cat_prefix}{cat}/")

            cmds = sorted(categories[cat])
            for m_idx, cmd in enumerate(cmds):
                is_last_cmd = (m_idx == len(cmds) - 1)
                
                # Adjust indent spacing depending on whether the category is last
                child_indent = "    " if is_last_cat else "│   "
                cmd_prefix = "└── " if is_last_cmd else "├── "
                
                tree_lines.append(f"{child_indent}{cmd_prefix}{prefix}{cmd}")

        tree_str = "\n".join(tree_lines)
        
        embed.description = f"Use `{prefix}help [command]` for command details.\n```\n{tree_str}\n```"
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))