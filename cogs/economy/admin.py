import discord
from discord.ext import commands
import aiosqlite
from .database import EconomyDB, DB_PATH

class EconomyAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addnodes")
    @commands.has_permissions(administrator=True)
    async def add_nodes(self, ctx, member: discord.Member, amount: int):
        """Add nodes to a user's balance."""
        if amount <= 0:
            return await ctx.send("❌ **Error:** Allocation amount must be greater than zero.")

        await EconomyDB.update_balance(
            user_id=member.id, 
            amount=amount, 
            action_type="ADMIN_ADD", 
            details=f"Nodes added by admin {ctx.author}"
        )
        await ctx.send(f"🟩 **Network Override:** Successfully allocated `+{amount:,}` Nodes to {member.mention}'s mainframe.")

    @commands.command(name="removenodes")
    @commands.has_permissions(administrator=True)
    async def remove_nodes(self, ctx, member: discord.Member, amount: int):
        """Remove nodes from a user's balance."""
        if amount <= 0:
            return await ctx.send("❌ **Error:** Extraction amount must be greater than zero.")

        # Pull user info to ensure they don't drop below zero unless you allow negative balances
        user_data = await EconomyDB.get_user(member.id)
        if user_data["nodes"] < amount:
            # Cap the extraction at their current wallet balance
            amount = user_data["nodes"]

        await EconomyDB.update_balance(
            user_id=member.id, 
            amount=-amount, 
            action_type="ADMIN_REMOVE", 
            details=f"Nodes removed by admin {ctx.author}"
        )
        await ctx.send(f"🟥 **Network Override:** Successfully extracted `-{amount:,}` Nodes from {member.mention}'s mainframe.")

    @commands.command(name="setnodes")
    @commands.has_permissions(administrator=True)
    async def set_nodes(self, ctx, member: discord.Member, amount: int):
        """Set a user's balance directly."""
        if amount < 0:
            return await ctx.send("❌ **Error:** Mainframe balances cannot be set below zero.")

        await EconomyDB.set_balance(member.id, amount)
        await ctx.send(f"⚡ **Network Override:** Forced {member.mention}'s wallet balance to exactly `{amount:,}` Nodes.")

    @commands.command(name="economyreset")
    @commands.has_permissions(administrator=True)
    async def economy_reset(self, ctx, member: discord.Member):
        """Reset a user's economy progress completely."""
        # Double-check confirmation prompt step can be added here if needed later, 
        # but let's go straight to database clearing for now.
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM economy_users WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM economy_logs WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM economy_inventory WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM passive_rigs WHERE user_id = ?", (member.id,))
            await db.commit()

        await ctx.send(f"☣️ **System Purge:** Completely wiped all node assets, histories, and data profiles for {member.mention}.")

    @commands.command(name="economylog")
    @commands.has_permissions(administrator=True)
    async def economy_log(self, ctx, member: discord.User = None):
        """View economy logs for a specific user."""
        # Default to the command author if no user is specified
        target_user = member or ctx.author
        
        async with aiosqlite.connect(DB_PATH) as db:
            # Filter the query by user_id and cap it at 25 items to prevent embed splitting
            async with db.execute(
                "SELECT action_type, amount, details, timestamp FROM economy_logs WHERE user_id = ? ORDER BY id DESC LIMIT 25", 
                (target_user.id,)
            ) as cursor:
                logs = await cursor.fetchall()

        if not logs:
            return await ctx.send(f"📄 No transaction history found for {target_user.mention}.")

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

        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(EconomyAdmin(bot))
