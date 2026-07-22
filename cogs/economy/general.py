import discord
from discord.ext import commands
from datetime import datetime, timedelta
from .database import EconomyDB
import time

class EconomyGeneral(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Custom Emojis
        self.TICK = "<:Tick:1514986183489360087>"
        self.CROSS = "<a:Cross:1514986232294281426>"

    @commands.Cog.listener()
    async def on_ready(self):
        # Automatically make sure tables exist when the bot boots up
        await EconomyDB.init_db()

    @commands.command(name="balance", aliases=["bal"])
    async def balance(self, ctx, member: discord.Member = None):
        """Checks your current matrix nodes wallet balance."""
        target = member or ctx.author
        
        try:
            profile = await EconomyDB.get_profile(target.id)
            
            if not profile:
                await EconomyDB.register_user(target.id)
                profile = await EconomyDB.get_profile(target.id)
            
            wallet_nodes = profile.get("nodes", 0)
            bank_nodes = profile.get("bank_nodes", profile.get("bank", 0))
            total_nodes = wallet_nodes + bank_nodes

            embed = discord.Embed(
                title=f"💳 Financial Telemetry: {target.display_name}", 
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            
            embed.add_field(name="🪙 Liquid Wallet", value=f"`{wallet_nodes:,}` Nodes", inline=True)
            embed.add_field(name="🏦 Secure Bank", value=f"`{bank_nodes:,}` Nodes", inline=True)
            embed.add_field(name="📊 Net Worth", value=f"`{total_nodes:,}` Nodes", inline=False)
            
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"❌ Error inside balance command: {e}")
            embed = discord.Embed(
                title=f"{self.CROSS} Data Loop Error",
                description="An internal data loop error occurred while compiling your balance sheet.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @commands.command(name="daily")
    async def daily(self, ctx):
        """Claim your daily node reward."""
        user_data = await EconomyDB.get_user(ctx.author.id)
        reward = 100  # Base daily reward amount
        current_time = time.time()
        
        # Cooldown check: 86400 seconds = 24 hours
        if user_data["last_daily"] and (current_time - user_data["last_daily"]) < 86400:
            time_left = 86400 - (current_time - user_data["last_daily"])
            hours, remainder = divmod(int(time_left), 3600)
            minutes, _ = divmod(remainder, 60)
            
            embed = discord.Embed(
                title=f"{self.CROSS} Firewall Lockout",
                description=f"You've already pulled daily nodes. Try again in **{hours}h {minutes}m**.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        # Update balance and save transaction record
        await EconomyDB.update_balance(ctx.author.id, nodes=reward)
        await EconomyDB.log_transaction(ctx.author.id, "DAILY", reward, "Claimed daily node reward")
        await EconomyDB.update_cooldown(ctx.author.id, "daily")
        
        embed = discord.Embed(
            title=f"{self.TICK} Data Stream Established!",
            description=f"You allocated `+{reward:,}` Nodes to your system.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="monthly")
    async def monthly(self, ctx):
        """Claim your monthly node reward."""
        user_data = await EconomyDB.get_user(ctx.author.id)
        reward = 3500  # Base monthly reward amount
        current_time = time.time()
        
        # Cooldown check: 2,592,000 seconds = 30 days
        if user_data["last_monthly"] and (current_time - user_data["last_monthly"]) < 2592000:
            time_left = 2592000 - (current_time - user_data["last_monthly"])
            days, remainder = divmod(int(time_left), 86400)
            hours, _ = divmod(remainder, 3600)
            
            embed = discord.Embed(
                title=f"{self.CROSS} Mainframe Cooldown",
                description=f"Monthly node drop is unavailable. Wait **{days}d {hours}h**.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        # Update balance and save transaction record
        await EconomyDB.update_balance(ctx.author.id, nodes=reward)
        await EconomyDB.log_transaction(ctx.author.id, "MONTHLY", reward, "Claimed monthly node reward")
        await EconomyDB.update_cooldown(ctx.author.id, "monthly")
        
        embed = discord.Embed(
            title=f"{self.TICK} Mainframe Sync Complete!",
            description=f"A massive injection of `+{reward:,}` Nodes has been successfully routed to your wallet.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="richest")
    async def richest(self, ctx):
        """View the richest users in the server."""
        try:
            leaderboard = await EconomyDB.get_leaderboard(10)
            if not leaderboard:
                embed = discord.Embed(
                    title="🏆 Server Top Node Mainframes",
                    description="The network ledger is currently empty. Start mining nodes to claim the top spot!",
                    color=discord.Color.gold()
                )
                embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
                return await ctx.send(embed=embed)

            embed = discord.Embed(
                title="🏆 Server Top Node Mainframes", 
                color=discord.Color.gold()
            )
            
            description = ""
            for index, (user_id, total_nodes) in enumerate(leaderboard, start=1):
                user = self.bot.get_user(user_id)
                
                if user is None:
                    try:
                        user = await self.bot.fetch_user(user_id)
                    except discord.NotFound:
                        user = None

                user_name = user.mention if user else f"Unknown User (`{user_id}`)"
                
                medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"`#{index}`"
                description += f"{medal} {user_name} — `{total_nodes:,.0f}` Nodes\n"
                
            embed.description = description
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            
            await ctx.send(embed=embed)

        except Exception as e:
            print(f"❌ Error inside richest command: {e}")
            embed = discord.Embed(
                title=f"{self.CROSS} Data Loop Error",
                description="An internal error occurred while fetching the network leaderboard.",
                color=discord.Color.dark_red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @commands.command(name="transactions", aliases=["tx"])
    async def transactions(self, ctx):
        """View your recent transaction log history."""
        history = await EconomyDB.get_history(ctx.author.id, 5)
        if not history:
            embed = discord.Embed(
                title="📝 Recent Network Log Ledger",
                description="No transaction data found on your network profile.",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        embed = discord.Embed(title="📝 Recent Network Log Ledger", color=discord.Color.blue())
        
        for row in history:
            action = row["action_type"]
            amount = row["amount"]
            details = row["details"]
            timestamp = row["timestamp"]
            
            clean_time = EconomyDB.format_timestamp(timestamp)
            sign = "+" if amount >= 0 else ""
            
            embed.add_field(
                name=f"[{action}] {sign}{amount:,} Nodes",
                value=f"└ *{details}*\n*🕒 {clean_time} UTC*",
                inline=False
            )
            
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)
    
    @commands.command(name="give", aliases=["transfer", "send"])
    async def pay(self, ctx, recipient: discord.Member, amount: int):
        """Transfer nodes from your wallet to another user."""
        # 1. Prevent transferring to yourself
        if recipient.id == ctx.author.id:
            embed = discord.Embed(
                title=f"{self.CROSS} Transfer Failed",
                description="You cannot transfer nodes to yourself.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        # 2. Prevent transferring negative or zero amounts
        if amount <= 0:
            embed = discord.Embed(
                title=f"{self.CROSS} Invalid Amount",
                description="Please specify a valid amount of nodes greater than `0`.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        try:
            # 3. Ensure sender profile exists
            sender_profile = await EconomyDB.get_profile(ctx.author.id)
            if not sender_profile:
                await EconomyDB.register_user(ctx.author.id)
                sender_profile = await EconomyDB.get_profile(ctx.author.id)

            # 4. Check if sender has enough liquid wallet balance
            sender_wallet = sender_profile.get("nodes", 0)
            if sender_wallet < amount:
                embed = discord.Embed(
                    title=f"{self.CROSS} Insufficient Funds",
                    description=f"You only have `{sender_wallet:,}` Nodes available in your liquid wallet.\n**Required:** `{amount:,}` Nodes",
                    color=discord.Color.gold()
                )
                embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
                return await ctx.send(embed=embed)

            # 5. Ensure recipient profile exists
            recipient_profile = await EconomyDB.get_profile(recipient.id)
            if not recipient_profile:
                await EconomyDB.register_user(recipient.id)

            # 6. Process the transfer
            await EconomyDB.update_balance(ctx.author.id, nodes=-amount)
            await EconomyDB.update_balance(recipient.id, nodes=amount)

            # 7. Log transaction records for both users
            await EconomyDB.log_transaction(
                ctx.author.id, "TRANSFER_SENT", -amount, f"Sent to {recipient.display_name}"
            )
            await EconomyDB.log_transaction(
                recipient.id, "TRANSFER_RECV", amount, f"Received from {ctx.author.display_name}"
            )

            # 8. Send confirmation embed
            embed = discord.Embed(
                title=f"{self.TICK} Network Transfer Complete",
                description=f"Successfully allocated `{amount:,}` Nodes from your wallet to {recipient.mention}.",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=recipient.display_avatar.url)
            embed.add_field(name="📤 Sender", value=ctx.author.mention, inline=True)
            embed.add_field(name="📥 Recipient", value=recipient.mention, inline=True)
            embed.add_field(name="🪙 Amount", value=f"`{amount:,}` Nodes", inline=False)
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)

            await ctx.send(embed=embed)

        except Exception as e:
            print(f"❌ Error inside pay command: {e}")
            embed = discord.Embed(
                title=f"{self.CROSS} Data Loop Error",
                description="An internal error occurred while processing the transaction.",
                color=discord.Color.dark_red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)