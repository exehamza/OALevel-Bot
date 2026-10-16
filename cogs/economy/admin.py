import discord
from discord.ext import commands
import aiosqlite
from .database import EconomyDB, DB_PATH

class EconomyAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Custom Emojis
        self.TICK = "<:Tick:1514986183489360087>"
        self.CROSS = "<a:Cross:1514986232294281426>"

    @commands.command(name="addnodes")
    @commands.has_permissions(administrator=True)
    async def add_nodes(self, ctx, member: discord.Member, amount: int):
        """Add nodes to a user's liquid wallet."""
        if amount <= 0:
            embed = discord.Embed(
                title=f"{self.CROSS} Invalid Allocation",
                description="Allocation amount must be greater than zero.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        await EconomyDB.update_balance(
            user_id=member.id, 
            nodes=amount, 
            action_type="ADMIN_ADD", 
            details=f"Nodes added to wallet by admin {ctx.author}"
        )

        updated = await EconomyDB.get_user(member.id)
        wallet_now = updated.get("nodes", 0)
        bank_now = updated.get("bank_nodes", 0)

        embed = discord.Embed(
            title=f"{self.TICK} Network Override Successful",
            description=(
                f"Allocated `+{amount:,}` Nodes to {member.mention}'s liquid wallet.\n\n"
                f"• **Liquid Wallet:** `{wallet_now:,}` Nodes\n"
                f"• **Secure Bank:** `{bank_now:,}` Nodes"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="removenodes")
    @commands.has_permissions(administrator=True)
    async def remove_nodes(self, ctx, member: discord.Member, amount: int):
        """Remove nodes from a user's liquid wallet first, spilling over into their secure bank if needed."""
        if amount <= 0:
            embed = discord.Embed(
                title=f"{self.CROSS} Invalid Extraction",
                description="Extraction amount must be greater than zero.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        user_data = await EconomyDB.get_user(member.id)
        wallet = user_data.get("nodes", 0) if user_data else 0
        bank = user_data.get("bank_nodes", 0) if user_data else 0

        if wallet + bank <= 0:
            embed = discord.Embed(
                title=f"{self.CROSS} Balance Already Zero",
                description=f"{member.mention} already has `0` Nodes across both their wallet and bank.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        # Drain liquid wallet first, then spill remaining extraction into secure bank
        from_wallet = min(wallet, amount)
        remaining = amount - from_wallet
        from_bank = min(bank, remaining)
        total_removed = from_wallet + from_bank

        await EconomyDB.update_balance(
            user_id=member.id, 
            nodes=-from_wallet, 
            bank=-from_bank, 
            action_type="ADMIN_REMOVE", 
            details=f"Removed by admin {ctx.author} (Wallet: -{from_wallet}, Bank: -{from_bank})"
        )

        new_wallet = wallet - from_wallet
        new_bank = bank - from_bank

        embed = discord.Embed(
            title=f"{self.TICK} Network Override Successful",
            description=(
                f"Extracted a total of `-{total_removed:,}` Nodes from {member.mention}.\n\n"
                f"• **Removed from Wallet:** `-{from_wallet:,}` (Now `{new_wallet:,}`)\n"
                f"• **Removed from Bank:** `-{from_bank:,}` (Now `{new_bank:,}`)"
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="setnodes")
    @commands.has_permissions(administrator=True)
    async def set_nodes(self, ctx, member: discord.Member, wallet: int, bank: int = 0):
        """Set a user's wallet and bank balance directly (bank defaults to 0)."""
        if wallet < 0 or bank < 0:
            embed = discord.Embed(
                title=f"{self.CROSS} Invalid Value",
                description="Mainframe balances cannot be set below zero.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        user_data = await EconomyDB.get_user(member.id)
        old_wallet = user_data.get("nodes", 0) if user_data else 0
        old_bank = user_data.get("bank_nodes", 0) if user_data else 0

        await EconomyDB.update_balance(
            user_id=member.id,
            nodes=wallet - old_wallet,
            bank=bank - old_bank,
            action_type="ADMIN_SET",
            details=f"Balance set by admin {ctx.author} (Wallet: {wallet}, Bank: {bank})"
        )

        embed = discord.Embed(
            title=f"{self.TICK} Balance Forced",
            description=(
                f"Updated {member.mention}'s total balance:\n\n"
                f"• **Liquid Wallet:** `{wallet:,}` Nodes\n"
                f"• **Secure Bank:** `{bank:,}` Nodes"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="economyreset")
    @commands.has_permissions(administrator=True)
    async def economy_reset(self, ctx, member: discord.Member):
        """Reset a user's economy progress completely."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM economy_users WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM economy_logs WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM economy_inventory WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM passive_rigs WHERE user_id = ?", (member.id,))
            await db.commit()

        embed = discord.Embed(
            title=f"{self.TICK} System Purge Complete",
            description=f"Completely wiped all node assets, histories, and data profiles for {member.mention}.",
            color=discord.Color.dark_red()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="economylog")
    @commands.has_permissions(administrator=True)
    async def economy_log(self, ctx, member: discord.User = None):
        """View economy logs for a specific user."""
        target_user = member or ctx.author
        
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT action_type, amount, details, timestamp FROM economy_logs WHERE user_id = ? ORDER BY id DESC LIMIT 25", 
                (target_user.id,)
            ) as cursor:
                logs = await cursor.fetchall()

        if not logs:
            embed = discord.Embed(
                title=f"🛡️ Audit Logs: {target_user.display_name}",
                description=f"No transaction history found for {target_user.mention}.",
                color=discord.Color.dark_red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            title=f"🛡️ Audit Logs: {target_user.display_name}", 
            color=discord.Color.dark_red()
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        for action, amount, details, timestamp in logs:
            clean_time = EconomyDB.format_timestamp(timestamp)
            
            embed.add_field(
                name=f"[{action}] | {clean_time} UTC",
                value=f"• **Delta:** `{amount:,}` Nodes\n• *\"{details}\"*",
                inline=False
            )

        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    # --- Blacklist Command Group ---

    @commands.group(name="economyblacklist", aliases=["ecoblacklist", "ecobl"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def economy_blacklist(self, ctx):
        """Parent command for managing economy blacklists."""
        embed = discord.Embed(
            title=f"{self.CROSS} Invalid Subcommand",
            description=(
                "Please specify a valid subcommand action:\n"
                "• `$economyblacklist add @member`\n"
                "• `$economyblacklist remove @member`"
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @economy_blacklist.command(name="add")
    @commands.has_permissions(administrator=True)
    async def blacklist_add(self, ctx, member: discord.Member):
        """Add a member to the economy blacklist."""
        added = await EconomyDB.add_blacklist(member.id, ctx.author.id)

        if not added:
            embed = discord.Embed(
                title=f"{self.CROSS} Already Blacklisted",
                description=f"{member.mention} is already blacklisted from the network economy.",
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            title=f"{self.TICK} Blacklist Applied",
            description=f"Successfully blacklisted {member.mention} from participating in the economy.",
            color=discord.Color.dark_red()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @economy_blacklist.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def blacklist_remove(self, ctx, member: discord.Member):
        """Remove a member from the economy blacklist."""
        removed = await EconomyDB.remove_blacklist(member.id)

        if not removed:
            embed = discord.Embed(
                title=f"{self.CROSS} Not Blacklisted",
                description=f"{member.mention} is not currently blacklisted.",
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            title=f"{self.TICK} Blacklist Revoked",
            description=f"Successfully restored economy access for {member.mention}.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
        
    @economy_blacklist.command(name="view", aliases=["list", "show"])
    @commands.has_permissions(administrator=True)
    async def blacklist_view(self, ctx):
        """List all members currently blacklisted from the economy."""
        blacklisted = await EconomyDB.get_all_blacklisted()

        if not blacklisted:
            embed = discord.Embed(
                title="🛡️ Economy Blacklist",
                description="There are currently no blacklisted users.",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        entries = []
        for entry in blacklisted:
            user_id = entry["user_id"]
            admin_id = entry["blacklisted_by"]
            ts = int(entry["timestamp"]) if entry["timestamp"] else None
            
            time_str = f"<t:{ts}:R>" if ts else "Unknown"
            entries.append(
                f"• **User:** <@{user_id}> (`{user_id}`)\n"
                f"  └ **By:** <@{admin_id}> | **When:** {time_str}"
            )

        description = "\n\n".join(entries[:15])
        if len(entries) > 15:
            description += f"\n\n*...and {len(entries) - 15} more.*"

        embed = discord.Embed(
            title=f"🚫 Blacklisted Users ({len(blacklisted)})",
            description=description,
            color=discord.Color.dark_red()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(EconomyAdmin(bot))
