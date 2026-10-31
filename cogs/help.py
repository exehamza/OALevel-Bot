import discord
from discord.ext import commands

# Server Role IDs (Moderator ---> Lead Moderator ---> Management)
ROLE_MODERATOR = 1256124924356071463
ROLE_LEAD_MOD = 1376227143545000056
ROLE_MANAGEMENT = 1272244827693650034

# Define permission hierarchy levels
PERM_MEMBER = 0
PERM_MOD = 1
PERM_LEAD_MOD = 2
PERM_MANAGEMENT = 3

# Central Data Repository
COMMAND_DATA = {
    # --- AI ---
    "ask": {
        "category": "AI",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<query>",
        "desc": "Asks the AI a question with LaTeX math rendering support."
    },

    # --- APPLICATIONS ---
    "setupapps": {
        "category": "Applications",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "",
        "desc": "Spawns the official staff application embed and button."
    },

    # --- AUTOMESSAGE (MANAGEMENT ONLY) ---
    "automessagesetup": {
        "category": "Auto Message",
        "level": PERM_MANAGEMENT,
        "aliases": ["amsetup"],
        "usage": "<time_interval> <session>",
        "desc": "Starts synchronized automatic rules notices across target channels."
    },
    "automessagestop": {
        "category": "Auto Message",
        "level": PERM_MANAGEMENT,
        "aliases": ["amstop"],
        "usage": "",
        "desc": "Stops automatic messages and deletes all active notice widgets."
    },

    # --- AUTOMOD ---
    "automod": {
        "category": "Auto Mod",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "",
        "desc": "Shows auto moderation configuration subcommands."
    },
    "automod add": {
        "category": "Auto Mod",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<word>",
        "desc": "Adds a word to the AutoMod blocked words list."
    },
    "automod remove": {
        "category": "Auto Mod",
        "level": PERM_MANAGEMENT,
        "aliases": ["delete"],
        "usage": "<word>",
        "desc": "Removes a word from the AutoMod blocked words list."
    },
    "automod view": {
        "category": "Auto Mod",
        "level": PERM_MANAGEMENT,
        "aliases": ["list"],
        "usage": "",
        "desc": "Shows all blocked words in the AutoMod filter."
    },
    "automod whitelist": {
        "category": "Auto Mod",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<@member>",
        "desc": "Toggles AutoMod chat filter immunity for a member."
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
        "desc": "Opens the dropdown menu to select or remove your custom name color."
    },

    # --- CONFESSIONS ---
    "setupconfessions": {
        "category": "Confessions",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "",
        "desc": "Spawns the anonymous confession submission prompt in the confession channel."
    },

    # --- ECONOMY: GENERAL, SHOP & CRIMES ---
    "balance": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["bal"],
        "usage": "[@member]",
        "desc": "Shows the liquid wallet, secure bank, and net worth of a member."
    },
    "buy": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<item_id> [quantity]",
        "desc": "Purchases an item, tool, key, or case from the economy shop."
    },
    "daily": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Claims your daily node reward."
    },
    "dep": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["deposit"],
        "usage": "<amount|all>",
        "desc": "Deposits nodes from your liquid wallet into your secure bank."
    },
    "give": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["transfer", "send"],
        "usage": "<@member> <amount>",
        "desc": "Transfers nodes from your wallet to another member with confirmation."
    },
    "hack": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<@member>",
        "desc": "Uses a Botnet to attempt a high-risk hack on another member's bank vault."
    },
    "inv": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["inventory"],
        "usage": "",
        "desc": "Shows all tools, keys, and cases in your inventory."
    },
    "monthly": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Claims your monthly node reward."
    },
    "open": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<case_id>",
        "desc": "Unlocks a loot case in your inventory using a Loot Box Key."
    },
    "richest": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Shows the top 10 richest members by combined wallet and bank nodes."
    },
    "rob": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<@member>",
        "desc": "Uses a Lockpick or Master Key to attempt stealing nodes from a member's wallet."
    },
    "shop": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Displays all available tools, keys, and loot cases in the Black Market Shop."
    },
    "transactions": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["tx"],
        "usage": "",
        "desc": "Shows your 5 most recent economy transactions."
    },
    "view": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["viewcase", "inspect"],
        "usage": "<case_id>",
        "desc": "Inspects the possible rewards inside a specific loot case."
    },
    "withdraw": {
        "category": "Economy",
        "level": PERM_MEMBER,
        "aliases": ["with"],
        "usage": "<amount|all>",
        "desc": "Withdraws nodes from your secure bank back into your liquid wallet."
    },

    # --- ECONOMY: MANAGEMENT ---
    "addnodes": {
        "category": "Economy Management",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Adds nodes directly to a member's liquid wallet."
    },
    "economyblacklist": {
        "category": "Economy Management",
        "level": PERM_MANAGEMENT,
        "aliases": ["ecoblacklist", "ecobl"],
        "usage": "",
        "desc": "Shows subcommands for managing the economy blacklist."
    },
    "economyblacklist add": {
        "category": "Economy Management",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<@member>",
        "desc": "Blacklists a member from participating in the economy."
    },
    "economyblacklist remove": {
        "category": "Economy Management",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<@member>",
        "desc": "Removes a member from the economy blacklist."
    },
    "economyblacklist view": {
        "category": "Economy Management",
        "level": PERM_MANAGEMENT,
        "aliases": ["list", "show"],
        "usage": "",
        "desc": "Lists all members currently blacklisted from the economy."
    },
    "economylog": {
        "category": "Economy Management",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "[@member|user_id]",
        "desc": "Shows up to 25 recent administrative economy audit logs for a user."
    },
    "economyreset": {
        "category": "Economy Management",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<@member>",
        "desc": "Completely wipes all node balances, logs, and inventory for a member."
    },
    "removenodes": {
        "category": "Economy Management",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Removes nodes from a member's liquid wallet first, then their secure bank."
    },
    "setnodes": {
        "category": "Economy Management",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<@member> <wallet> [bank]",
        "desc": "Sets a member's liquid wallet and secure bank balances directly."
    },

    # --- GAMES ---
    "coinflip": {
        "category": "Games",
        "level": PERM_MEMBER,
        "aliases": ["cf"],
        "usage": "<bet|all>",
        "desc": "Flips a coin to double or lose your node bet."
    },
    "slots": {
        "category": "Games",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<bet|all>",
        "desc": "Plays the slot machine with a node bet."
    },

    # --- KEYWORDS ---
    "keyword": {
        "category": "Keywords",
        "level": PERM_MANAGEMENT,
        "aliases": ["keywords"],
        "usage": "",
        "desc": "Shows keyword auto-responder configuration subcommands."
    },
    "keyword add": {
        "category": "Keywords",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<trigger> | <response>",
        "desc": "Adds or updates an automatic keyword trigger and response."
    },
    "keyword remove": {
        "category": "Keywords",
        "level": PERM_MANAGEMENT,
        "aliases": ["delete"],
        "usage": "<trigger>",
        "desc": "Removes a keyword trigger from the auto-responder list."
    },
    "keyword view": {
        "category": "Keywords",
        "level": PERM_MANAGEMENT,
        "aliases": ["list"],
        "usage": "",
        "desc": "Displays all saved keyword triggers and responses with pagination."
    },

    # --- LEVELS ---
    "leaderboard": {
        "category": "Levels",
        "level": PERM_MEMBER,
        "aliases": ["lb"],
        "usage": "",
        "desc": "Displays the top 10 server members by XP and level."
    },
    "level": {
        "category": "Levels",
        "level": PERM_MEMBER,
        "aliases": ["rank"],
        "usage": "[@member]",
        "desc": "Displays the rank card, current level, and XP progress of a member."
    },
    "xp": {
        "category": "Levels",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "",
        "desc": "Shows XP management subcommands."
    },
    "xp add": {
        "category": "Levels",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Adds XP points to a member and updates their level."
    },
    "xp remove": {
        "category": "Levels",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Removes XP points from a member and updates their level."
    },

    # --- LOCKIN ---
    "lockin": {
        "category": "Lockin",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<10m-24h>",
        "desc": "Times yourself out for a set duration (10m to 24h) to focus on studying."
    },

    # --- MODERATION ---
    "ban": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": [],
        "usage": "<@member> [reason]",
        "desc": "Permanently bans a member from the server and logs the case."
    },
    "kick": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": [],
        "usage": "<@member> [reason]",
        "desc": "Kicks a member from the server and logs the case."
    },
    "logs": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": ["history", "cases"],
        "usage": "<@member|user_id>",
        "desc": "Shows paginated moderation case history for a user."
    },
    "mute": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": ["timeout"],
        "usage": "<@member> <duration> [reason]",
        "desc": "Mutes (times out) a member for a duration (e.g., 10m, 2h, 1d)."
    },
    "purge": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": ["clear"],
        "usage": "[@member] <amount>",
        "desc": "Bulk deletes up to 100 messages in the channel, optionally filtered by user."
    },
    "removecase": {
        "category": "Moderation",
        "level": PERM_MANAGEMENT,
        "aliases": ["delcase", "deletecase"],
        "usage": "<case_id>",
        "desc": "Deletes a specific moderation case record by its Case ID."
    },
    "reply": {
        "category": "Moderation",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "[#channel] <message_id> <message>",
        "desc": "Replies to a specific message ID in the current or specified channel through the bot."
    },
    "say": {
        "category": "Moderation",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<message>",
        "desc": "Deletes your command and sends the message through the bot."
    },
    "snipe": {
        "category": "Moderation",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "[1-5]",
        "desc": "Snipes up to the last 5 recently deleted messages in the current channel."
    },
    "unban": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": [],
        "usage": "<username|ID>",
        "desc": "Removes a server ban from a user by their username, tag, or User ID."
    },
    "unmute": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": ["untimeout"],
        "usage": "<@member> [reason]",
        "desc": "Removes an active timeout from a muted member."
    },
    "warn": {
        "category": "Moderation",
        "level": PERM_MOD,
        "aliases": [],
        "usage": "<@member> [reason]",
        "desc": "Warns a member via DM and records the infraction in moderation logs."
    },

    # --- MODMAIL (LEAD MODERATOR & MANAGEMENT ONLY) ---
    "close": {
        "category": "Modmail",
        "level": PERM_LEAD_MOD,
        "aliases": [],
        "usage": "",
        "desc": "Closes, locks, and archives an active modmail ticket thread."
    },
    "modmailblacklist": {
        "category": "Modmail",
        "level": PERM_LEAD_MOD,
        "aliases": ["mmblacklist", "mmbl"],
        "usage": "",
        "desc": "Shows subcommands for managing the modmail ticket blacklist."
    },
    "modmailblacklist add": {
        "category": "Modmail",
        "level": PERM_LEAD_MOD,
        "aliases": [],
        "usage": "<@user|user_id>",
        "desc": "Blacklists a user from opening modmail tickets via DM."
    },
    "modmailblacklist remove": {
        "category": "Modmail",
        "level": PERM_LEAD_MOD,
        "aliases": ["delete"],
        "usage": "<@user|user_id>",
        "desc": "Removes a user from the modmail ticket blacklist."
    },
    "modmailblacklist view": {
        "category": "Modmail",
        "level": PERM_LEAD_MOD,
        "aliases": ["list", "show"],
        "usage": "",
        "desc": "Lists all users currently blacklisted from opening modmail tickets."
    },

    # --- NICKNAME ---
    "sn": {
        "category": "Nickname",
        "level": PERM_MOD,
        "aliases": [],
        "usage": "<@member> [nickname]",
        "desc": "Changes a member's nickname, or resets it if no nickname is given."
    },

    # --- REPUTATION ---
    "rep": {
        "category": "Reputation",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "[@member]",
        "desc": "Shows the current reputation points of yourself or another member."
    },
    "replb": {
        "category": "Reputation",
        "level": PERM_MEMBER,
        "aliases": ["repleaderboard", "lbrep"],
        "usage": "",
        "desc": "Displays the top 10 members with the highest reputation points."
    },
    "setrep": {
        "category": "Reputation",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<@member> <amount>",
        "desc": "Sets a member's reputation points to a specific amount."
    },

    # --- RULES ---
    "rule": {
        "category": "Rules",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<1-14>",
        "desc": "Displays a specific server rule by number (1 to 14)."
    },
    "setuprules": {
        "category": "Rules",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "",
        "desc": "Posts the complete server rules embed in the current channel."
    },

    # --- SERVER STATISTICS (STATBOT) ---
    "channel": {
        "category": "Server Statistics",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "[#channel] [days]",
        "desc": "See a channel's stats."
    },
    "chart": {
        "category": "Server Statistics",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "[messages|voice|members|#channel|@user] [days]",
        "desc": "Generate a detailed chart."
    },
    "me": {
        "category": "Server Statistics",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "[days]",
        "desc": "See your stats in this server."
    },
    "server": {
        "category": "Server Statistics",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "[days]",
        "desc": "See an overview of the server's stats."
    },
    "stats": {
        "category": "Server Statistics",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "[messages|voice|members] [days]",
        "desc": "See an overview of a type of stats."
    },
    "top": {
        "category": "Server Statistics",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "[messages|voice|channels] [days]",
        "desc": "See a list of top members and channels."
    },
    "user": {
        "category": "Server Statistics",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "[@member] [days]",
        "desc": "See a user's stats in this server."
    },

    # --- SLOWMODE ---
    "slowmode": {
        "category": "Slowmode",
        "level": PERM_MOD,
        "aliases": ["sm"],
        "usage": "[duration|0]",
        "desc": "Checks, sets (e.g., 5s, 2m, 1h), or disables (0) the channel slowmode."
    },

    # --- TRANSLATE ---
    "langs": {
        "category": "Translate",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "",
        "desc": "Shows common supported translation languages and their short codes."
    },
    "tr": {
        "category": "Translate",
        "level": PERM_MEMBER,
        "aliases": [],
        "usage": "<target_lang> (reply to message)",
        "desc": "Translates the message you replied to into the specified target language."
    },

    # --- UTILITY ---
    "botstatus": {
        "category": "Utility",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "",
        "desc": "Fetches the host server systemd service status for the bot."
    },
    "export": {
        "category": "Utility",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<filename>",
        "desc": "Exports a database or JSON file from the data/ folder (e.g., economy.db)."
    },
    "ping": {
        "category": "Utility",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "[host]",
        "desc": "Checks Discord API latency or pings an external network host."
    },
    "steal": {
        "category": "Utility",
        "level": PERM_MANAGEMENT,
        "aliases": [],
        "usage": "<custom_emoji> | (reply to sticker)",
        "desc": "Steals a custom emoji or replied-to sticker and adds it to the server."
    }
}


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.remove_command("help")

    def get_user_level(self, ctx: commands.Context) -> int:
        """Determines the user's permission level based on the server role hierarchy."""
        if not ctx.guild:
            return PERM_MEMBER

        role_ids = {role.id for role in ctx.author.roles}
        perms = ctx.author.guild_permissions

        # 1. Management (1272244827693650034) / Administrator / Server Owner
        if (
            ROLE_MANAGEMENT in role_ids
            or perms.administrator
            or ctx.author == ctx.guild.owner
        ):
            return PERM_MANAGEMENT

        # 2. Lead Moderator (1376227143545000056)
        if ROLE_LEAD_MOD in role_ids:
            return PERM_LEAD_MOD

        # 3. Regular Moderator (1256124924356071463)
        if (
            ROLE_MODERATOR in role_ids
            or perms.manage_messages
            or perms.kick_members
            or perms.ban_members
            or perms.moderate_members
            or perms.manage_nicknames
        ):
            return PERM_MOD

        return PERM_MEMBER

    def find_command_entry(self, query: str):
        """Finds a command in COMMAND_DATA by exact name, alias, or parent+subcommand alias."""
        query = query.lower().strip()

        for name, data in COMMAND_DATA.items():
            if query == name or query in data.get("aliases", []):
                return name, data

        parts = query.split()
        if len(parts) == 2:
            parent_q, sub_q = parts[0], parts[1]
            resolved_parent = parent_q
            for name, data in COMMAND_DATA.items():
                if " " not in name and (parent_q == name or parent_q in data.get("aliases", [])):
                    resolved_parent = name
                    break

            for name, data in COMMAND_DATA.items():
                if " " in name:
                    p_name, s_name = name.split(" ", 1)
                    if p_name == resolved_parent and (sub_q == s_name or sub_q in data.get("aliases", [])):
                        return name, data

        return None, None

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context, *, query: str = None):
        """Displays filtered help commands or details for a specific command."""
        user_level = self.get_user_level(ctx)
        prefix = ctx.clean_prefix

        # --- CASE 1: SPECIFIC COMMAND HELP ($help <command>) ---
        if query:
            if query.startswith(prefix):
                query = query[len(prefix):].strip()

            target_name, target_info = self.find_command_entry(query)

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
            
            level_labels = {
                PERM_MEMBER: "Member",
                PERM_MOD: "Moderator",
                PERM_LEAD_MOD: "Lead Moderator",
                PERM_MANAGEMENT: "Management"
            }
            embed.add_field(name="Required Role", value=level_labels.get(target_info["level"], "Member"), inline=True)
            
            await ctx.send(embed=embed)
            return

        # --- CASE 2: MAIN HELP MENU ($help) ---
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

        tree_lines = ["Commands/"]
        sorted_cats = sorted(categories.keys())

        for c_idx, cat in enumerate(sorted_cats):
            is_last_cat = (c_idx == len(sorted_cats) - 1)
            cat_prefix = "└── " if is_last_cat else "├── "
            tree_lines.append(f"{cat_prefix}{cat}/")

            cmds = sorted(categories[cat])
            for m_idx, cmd in enumerate(cmds):
                is_last_cmd = (m_idx == len(cmds) - 1)
                child_indent = "    " if is_last_cat else "│   "
                cmd_prefix = "└── " if is_last_cmd else "├── "
                tree_lines.append(f"{child_indent}{cmd_prefix}{prefix}{cmd}")

        tree_str = "\n".join(tree_lines)
        
        embed.description = f"Use `{prefix}help [command]` for command details.\n```\n{tree_str}\n```"
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
