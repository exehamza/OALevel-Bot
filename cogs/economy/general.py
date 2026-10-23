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


class TransferConfirmView(discord.ui.View):
    def __init__(self, cog, ctx: commands.Context, recipient: discord.Member, amount: int, tax_amount: int, received_amount: int, is_top_3: bool):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.recipient = recipient
        self.amount = amount
        self.tax_amount = tax_amount
        self.received_amount = received_amount
        self.is_top_3 = is_top_3
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Only the sender of this transfer can confirm or cancel it.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm Transfer", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()

        # Re-verify sender balance at confirmation time to prevent double-spending
        sender_profile = await EconomyDB.get_profile(self.ctx.author.id)
        sender_wallet = sender_profile.get("nodes", 0) if sender_profile else 0

        if sender_wallet < self.amount:
            embed = discord.Embed(
                title=f"{self.cog.CROSS} Transfer Failed — Insufficient Funds",
                description=(
                    f"Your wallet balance changed before confirming! You only have `{sender_wallet:,}` Nodes available.\n"
                    f"**Required:** `{self.amount:,}` Nodes"
                ),
                color=discord.Color.red(),
            )
            embed.set_footer(
                text=f"Requested by {self.ctx.author.name}",
                icon_url=self.ctx.author.display_avatar.url,
            )
            return await interaction.message.edit(embed=embed, view=None)

        recipient_profile = await EconomyDB.get_profile(self.recipient.id)
        if not recipient_profile:
            await EconomyDB.register_user(self.recipient.id)

        await EconomyDB.update_balance(self.ctx.author.id, nodes=-self.amount)
        await EconomyDB.update_balance(self.recipient.id, nodes=self.received_amount)

        await EconomyDB.log_transaction(
            self.ctx.author.id,
            "TRANSFER_SENT",
            -self.amount,
            f"Sent to {self.recipient.display_name} (Tax: {self.tax_amount:,})",
        )
        await EconomyDB.log_transaction(
            self.recipient.id,
            "TRANSFER_RECV",
            self.received_amount,
            f"Received from {self.ctx.author.display_name}",
        )

        embed = discord.Embed(
            title=f"{self.cog.TICK} Network Transfer Complete",
            description=f"Successfully transferred Nodes from your wallet to {self.recipient.mention}.",
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=self.recipient.display_avatar.url)
        embed.add_field(name="📤 Sender", value=self.ctx.author.mention, inline=True)
        embed.add_field(name="📥 Recipient", value=self.recipient.mention, inline=True)

        if self.tax_amount > 0:
            embed.add_field(
                name="🪙 Transfer Breakdown",
                value=(
                    f"• **Gross Sent:** `{self.amount:,}` Nodes\n"
                    f"• **Network Tax (15%):** `-{self.tax_amount:,}` Nodes\n"
                    f"• **Net Received:** `+{self.received_amount:,}` Nodes"
                ),
                inline=False,
            )
        else:
            exemption_note = " *(Top 3 Leaderboard VIP Exemption)*" if self.is_top_3 and self.amount > 10000 else ""
            embed.add_field(
                name="🪙 Amount Received",
                value=f"`{self.received_amount:,}` Nodes{exemption_note}",
                inline=False,
            )

        embed.set_footer(
            text=f"Requested by {self.ctx.author.name}",
            icon_url=self.ctx.author.display_avatar.url,
        )
        await interaction.message.edit(embed=embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()

        embed = discord.Embed(
            title=f"{self.cog.CROSS} Transfer Cancelled",
            description=f"Cancelled the transfer of `{self.amount:,}` Nodes to {self.recipient.mention}.",
            color=discord.Color.red(),
        )
        embed.set_footer(
            text=f"Requested by {self.ctx.author.name}",
            icon_url=self.ctx.author.display_avatar.url,
        )
        await interaction.message.edit(embed=embed, view=None)

    async def on_timeout(self):
        if self.message:
            embed = discord.Embed(
                title=f"{self.cog.CROSS} Transfer Timed Out",
                description="You did not confirm the transfer within 60 seconds. No Nodes were deducted.",
                color=discord.Color.red(),
            )
            embed.set_footer(
                text=f"Requested by {self.ctx.author.name}",
                icon_url=self.ctx.author.display_avatar.url,
            )
            try:
                await self.message.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass


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
        if ctx.author.guild_permissions.administrator:
            return True

        if await EconomyDB.is_blacklisted(ctx.author.id):
            await ctx.send("❌ You are blacklisted from using the network economy.")
            return False
        return True

    @commands.Cog.listener()
    async def on_ready(self):
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

        reward = 100
        current_time = time.time()
        last_daily = user_data.get("last_daily") if user_data else None

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

        reward = 3500
        current_time = time.time()
        last_monthly = user_data.get("last_monthly") if user_data else None

        if last_monthly and (current_time - last_monthly) < 2592000:
            time_left = 2592000 - (current_time - last_monthly)
            days, remainder = divmod(int(time_left), 86400)
            hours, _ = divmod(remainder, 3600)

            embed = discord.Embed(
                title=f"{self.CROSS} Mainframe Cooldown",
                description=(
                    f"Monthly node drop is unavailable. Wait **{days}d"
                    f" {hours}h**."
                ),
                color=discord.Color.red(),
            )
            embed.set_footer(
                text=f"Requested by {ctx.author.name}",
                icon_url=ctx.author.display_avatar.url,
            )
            return await ctx.send(embed=embed)

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
        """Transfer nodes from your wallet to another user (with confirmation)."""
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

            # 7. Prompt sender for confirmation before executing
            confirm_embed = discord.Embed(
                title="⚠️ Confirm Network Transfer",
                description=f"Are you sure you want to send Nodes to {recipient.mention}?",
                color=discord.Color.gold(),
            )
            confirm_embed.set_thumbnail(url=recipient.display_avatar.url)
            confirm_embed.add_field(name="📤 Sender", value=ctx.author.mention, inline=True)
            confirm_embed.add_field(name="📥 Recipient", value=recipient.mention, inline=True)

            if tax_amount > 0:
                confirm_embed.add_field(
                    name="🪙 Transfer Breakdown",
                    value=(
                        f"• **Gross Sent:** `{amount:,}` Nodes\n"
                        f"• **Network Tax (15%):** `-{tax_amount:,}` Nodes\n"
                        f"• **Net Recipient Gets:** `+{received_amount:,}` Nodes"
                    ),
                    inline=False,
                )
            else:
                exemption_note = " *(Top 3 Leaderboard VIP Exemption)*" if is_top_3 and amount > 10000 else ""
                confirm_embed.add_field(
                    name="🪙 Amount to Transfer",
                    value=f"`{received_amount:,}` Nodes{exemption_note}",
                    inline=False,
                )

            confirm_embed.set_footer(
                text=f"Requested by {ctx.author.name} • Expires in 60s",
                icon_url=ctx.author.display_avatar.url,
            )

            view = TransferConfirmView(
                cog=self,
                ctx=ctx,
                recipient=recipient,
                amount=amount,
                tax_amount=tax_amount,
                received_amount=received_amount,
                is_top_3=is_top_3,
            )
            sent_msg = await ctx.send(embed=confirm_embed, view=view)
            view.message = sent_msg

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
