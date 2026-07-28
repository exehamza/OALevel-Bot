import time
from datetime import datetime, timedelta
import discord
from discord.ext import commands
from .database import EconomyDB


def not_in_thread():
    """Custom command check to block execution inside threads."""

    async def predicate(ctx):
        if isinstance(ctx.channel, discord.Thread):
            raise commands.CheckFailure(
                "This command cannot be used inside threads."
            )
        return True

    return commands.check(predicate)


class EconomyGeneral(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        # Custom Emojis
        self.TICK = "<:Tick:1514986183489360087>"
        self.CROSS = "<a:Cross:1514986232294281426>"

    async def cog_command_error(self, ctx, error):
        """Cog-wide error handler to capture check failures (e.g. threads)."""
        if isinstance(error, commands.CheckFailure) and "threads" in str(error):
            embed = discord.Embed(
                description=f"{self.CROSS} This command cannot be used inside threads.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            
    async def cog_check(self, ctx):
        # Exempt administrators from checking, or let them execute admin commands
        if ctx.author.guild_permissions.administrator:
            return True

        if await EconomyDB.is_blacklisted(ctx.author.id):
            await ctx.send("❌ You are blacklisted from using the network economy.")
            return False
        return True

    @commands.Cog.listener()
    async def on_ready(self):
        # Automatically make sure tables exist when the bot boots up
        await EconomyDB.init_db()

    @commands.command(name="balance", aliases=["bal"])
    @not_in_thread()
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
                color=discord.Color.blue(),
            )
            embed.set_thumbnail(url=target.display_avatar.url)

            embed.add_field(
                name="🪙 Liquid Wallet",
                value=f"`{wallet_nodes:,}` Nodes",
                inline=True,
            )
            embed.add_field(
                name="🏦 Secure Bank",
                value=f"`{bank_nodes:,}` Nodes",
                inline=True,
            )
            embed.add_field(
                name="📊 Net Worth",
                value=f"`{total_nodes:,}` Nodes",
                inline=False,
            )

            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )

            await ctx.send(embed=embed)

        except Exception as e:
            print(f"❌ Error inside balance command: {e}")
            embed = discord.Embed(
                title=f"{self.CROSS} Data Loop Error",
                description=(
                    "An internal data loop error occurred while compiling your"
                    " balance sheet."
                ),
                color=discord.Color.red(),
            )
            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
            await ctx.send(embed=embed)

    @commands.command(name="daily")
    @not_in_thread()
    async def daily(self, ctx):
        """Claim your daily node reward."""
        user_data = await EconomyDB.get_user(ctx.author.id)
        if not user_data:
            await EconomyDB.register_user(ctx.author.id)
            user_data = await EconomyDB.get_user(ctx.author.id)

        reward = 100  # Base daily reward amount
        current_time = time.time()
        last_daily = user_data.get("last_daily") if user_data else None

        # Cooldown check: 86400 seconds = 24 hours
        if last_daily and (current_time - last_daily) < 86400:
            time_left = 86400 - (current_time - last_daily)
            hours, remainder = divmod(int(time_left), 3600)
            minutes, _ = divmod(remainder, 60)

            embed = discord.Embed(
                title=f"{self.CROSS} Firewall Lockout",
                description=(
                    "You've already pulled daily nodes. Try again in"
                    f" **{hours}h {minutes}m**."
                ),
                color=discord.Color.red(),
            )
            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
            return await ctx.send(embed=embed)

        # Update balance and save transaction record
        await EconomyDB.update_balance(ctx.author.id, nodes=reward)
        await EconomyDB.log_transaction(
            ctx.author.id, "DAILY", reward, "Claimed daily node reward"
        )
        await EconomyDB.update_cooldown(ctx.author.id, "daily")

        embed = discord.Embed(
            title=f"{self.TICK} Data Stream Established!",
            description=f"You allocated `+{reward:,}` Nodes to your system.",
            color=discord.Color.green(),
        )
        embed.set_footer(
            text=f"Requested by {ctx.author.name}",
            icon_url=ctx.author.display_avatar.url,
        )
        await ctx.send(embed=embed)

    @commands.command(name="monthly")
    @not_in_thread()
    async def monthly(self, ctx):
        """Claim your monthly node reward."""
        user_data = await EconomyDB.get_user(ctx.author.id)
        if not user_data:
            await EconomyDB.register_user(ctx.author.id)
            user_data = await EconomyDB.get_user(ctx.author.id)

        reward = 3500  # Base monthly reward amount
        current_time = time.time()
        last_monthly = user_data.get("last_monthly") if user_data else None

        # Cooldown check: 2,592,000 seconds = 30 days
        if last_monthly and (current_time - last_monthly) < 2592000:
            time_left = 2592000 - (current_time - last_monthly)
            days, remainder = divmod(int(time_left), 86400)
            hours, _ = divmod(remainder, 3600)

            embed = discord.Embed(
                title=f"{self.CROSS} Mainframe Cooldown",
                description=(
                    "Monthly node drop is unavailable. Wait **{days}d"
                    " {hours}h**."
                ),
                color=discord.Color.red(),
            )
            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
            return await ctx.send(embed=embed)

        # Update balance and save transaction record
        await EconomyDB.update_balance(ctx.author.id, nodes=reward)
        await EconomyDB.log_transaction(
            ctx.author.id, "MONTHLY", reward, "Claimed monthly node reward"
        )
        await EconomyDB.update_cooldown(ctx.author.id, "monthly")

        embed = discord.Embed(
            title=f"{self.TICK} Mainframe Sync Complete!",
            description=(
                f"A massive injection of `+{reward:,}` Nodes has been"
                " successfully routed to your wallet."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(
            text=f"Requested by {ctx.author.name}",
            icon_url=ctx.author.display_avatar.url,
        )
        await ctx.send(embed=embed)

    @commands.command(name="richest")
    @not_in_thread()
    async def richest(self, ctx):
        """View the richest users in the server."""
        try:
            leaderboard = await EconomyDB.get_leaderboard(10)
            if not leaderboard:
                embed = discord.Embed(
                    title="🏆 Server Top Node Mainframes",
                    description=(
                        "The network ledger is currently empty. Start mining"
                        " nodes to claim the top spot!"
                    ),
                    color=discord.Color.gold(),
                )
                embed.set_footer(
                    text=f"Requested by {ctx.author.name}",
                    icon_url=ctx.author.display_avatar.url,
                )
                return await ctx.send(embed=embed)

            embed = discord.Embed(
                title="🏆 Server Top Node Mainframes",
                color=discord.Color.gold(),
            )

            description = ""
            for index, (user_id, total_nodes) in enumerate(
                leaderboard, start=1
            ):
                user = self.bot.get_user(user_id)

                if user is None:
                    try:
                        user = await self.bot.fetch_user(user_id)
                    except discord.NotFound:
                        user = None

                user_name = (
                    user.mention if user else f"Unknown User (`{user_id}`)"
                )

                medal = (
                    "🥇"
                    if index == 1
                    else "🥈" if index == 2 else "🥉" if index == 3 else f"`#{index}`"
                )
                description += (
                    f"{medal} {user_name} — `{total_nodes:,.0f}` Nodes\n"
                )

            embed.description = description
            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )

            await ctx.send(embed=embed)

        except Exception as e:
            print(f"❌ Error inside richest command: {e}")
            embed = discord.Embed(
                title=f"{self.CROSS} Data Loop Error",
                description=(
                    "An internal error occurred while fetching the network"
                    " leaderboard."
                ),
                color=discord.Color.dark_red(),
            )
            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
            await ctx.send(embed=embed)

    @commands.command(name="transactions", aliases=["tx"])
    @not_in_thread()
    async def transactions(self, ctx):
        """View your recent transaction log history."""
        history = await EconomyDB.get_history(ctx.author.id, 5)
        if not history:
            embed = discord.Embed(
                title="📝 Recent Network Log Ledger",
                description=(
                    "No transaction data found on your network profile."
                ),
                color=discord.Color.blue(),
            )
            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            title="📝 Recent Network Log Ledger", color=discord.Color.blue()
        )

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
                inline=False,
            )

        embed.set_footer(
            text=f"Requested by {ctx.author.name}",
            icon_url=ctx.author.display_avatar.url,
        )
        await ctx.send(embed=embed)

    @commands.command(name="give", aliases=["transfer", "send"])
    @not_in_thread()
    async def pay(self, ctx, recipient: discord.Member, amount: int):
        """Transfer nodes from your wallet to another user."""
        # 1. Prevent transferring to yourself
        if recipient.id == ctx.author.id:
            embed = discord.Embed(
                title=f"{self.CROSS} Transfer Failed",
                description="You cannot transfer nodes to yourself.",
                color=discord.Color.red(),
            )
            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
            return await ctx.send(embed=embed)

        # 2. Prevent transferring negative or zero amounts
        if amount <= 0:
            embed = discord.Embed(
                title=f"{self.CROSS} Invalid Amount",
                description=(
                    "Please specify a valid amount of nodes greater than `0`."
                ),
                color=discord.Color.red(),
            )
            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
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
                    description=(
                        f"You only have `{sender_wallet:,}` Nodes available in"
                        f" your liquid wallet.\n**Required:** `{amount:,}` Nodes"
                    ),
                    color=discord.Color.gold(),
                )
                embed.set_footer(
                    text=f"Requested by {ctx.author.name}",
                    icon_url=ctx.author.display_avatar.url,
                )
                return await ctx.send(embed=embed)

            # 5. Check if sender is in the top 3 on the richest leaderboard
            leaderboard = await EconomyDB.get_leaderboard(3)
            top_3_ids = [user_id for user_id, _ in leaderboard] if leaderboard else []
            is_top_3 = ctx.author.id in top_3_ids

            # 6. Calculate tax (15% for amounts > 10,000, 0% if sender is in top 3)
            tax_amount = 0
            if amount > 10000 and not is_top_3:
                tax_amount = int(amount * 0.15)

            received_amount = amount - tax_amount

            # 7. Ensure recipient profile exists
            recipient_profile = await EconomyDB.get_profile(recipient.id)
            if not recipient_profile:
                await EconomyDB.register_user(recipient.id)

            # 8. Process the transfer
            await EconomyDB.update_balance(ctx.author.id, nodes=-amount)
            await EconomyDB.update_balance(recipient.id, nodes=received_amount)

            # 9. Log transaction records for both users
            await EconomyDB.log_transaction(
                ctx.author.id,
                "TRANSFER_SENT",
                -amount,
                f"Sent to {recipient.display_name} (Tax: {tax_amount:,})",
            )
            await EconomyDB.log_transaction(
                recipient.id,
                "TRANSFER_RECV",
                received_amount,
                f"Received from {ctx.author.display_name}",
            )

            # 10. Send confirmation embed
            embed = discord.Embed(
                title=f"{self.TICK} Network Transfer Complete",
                description=(
                    f"Successfully transferred Nodes from your wallet to {recipient.mention}."
                ),
                color=discord.Color.green(),
            )
            embed.set_thumbnail(url=recipient.display_avatar.url)
            embed.add_field(
                name="📤 Sender", value=ctx.author.mention, inline=True
            )
            embed.add_field(
                name="📥 Recipient", value=recipient.mention, inline=True
            )
            
            if tax_amount > 0:
                embed.add_field(
                    name="🪙 Transfer Breakdown",
                    value=(
                        f"• **Gross Sent:** `{amount:,}` Nodes\n"
                        f"• **Network Tax (15%):** `-{tax_amount:,}` Nodes\n"
                        f"• **Net Received:** `+{received_amount:,}` Nodes"
                    ),
                    inline=False,
                )
            else:
                exemption_note = " *(Top 3 Leaderboard VIP Exemption)*" if is_top_3 and amount > 10000 else ""
                embed.add_field(
                    name="🪙 Amount Received",
                    value=f"`{received_amount:,}` Nodes{exemption_note}",
                    inline=False,
                )

            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )

            await ctx.send(embed=embed)

        except Exception as e:
            print(f"❌ Error inside pay command: {e}")
            embed = discord.Embed(
                title=f"{self.CROSS} Data Loop Error",
                description=(
                    "An internal error occurred while processing the"
                    " transaction."
                ),
                color=discord.Color.dark_red(),
            )
            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(EconomyGeneral(bot))