import random
import asyncio
import time
import discord
from discord.ext import commands
from .database import EconomyDB

ROB_COOLDOWN_SECONDS = 900    # 15 minutes
HACK_COOLDOWN_SECONDS = 1800  # 30 minutes


class EconomyCrimes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Track cooldowns manually so timers ONLY start when a real attack happens
        self._rob_cooldowns: dict[int, float] = {}
        self._hack_cooldowns: dict[int, float] = {}

    def _calculate_weighted_steal_percentage(self) -> int:
        """
        Calculates a stolen percentage between 5% and 90% in 5% increments.
        Higher percentages are significantly harder to roll.
        """
        percentages = list(range(5, 95, 5))  # [5, 10, 15, ..., 90]
        weights = [100, 80, 65, 50, 38, 28, 20, 14, 10, 7, 5, 3, 2, 1, 1, 0.5, 0.3, 0.2]
        return random.choices(percentages, weights=weights, k=1)[0]

    def _check_cooldown(self, mapping: dict[int, float], user_id: int) -> int:
        """Returns remaining cooldown seconds (0 if ready)."""
        remaining = int(mapping.get(user_id, 0) - time.time())
        return max(0, remaining)

    async def _send_cooldown_embed(self, ctx: commands.Context, retry_after: int):
        minutes, seconds = divmod(retry_after, 60)
        hours, minutes = divmod(minutes, 60)
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m {seconds}s"

        embed = discord.Embed(
            title="⏳ On Cooldown",
            description=f"You need to lie low for a bit! Please wait **{time_str}** before trying another crime.",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="rob")
    async def rob_user(self, ctx: commands.Context, member: discord.Member):
        """Attempt to steal nodes from another user's wallet."""
        retry_after = self._check_cooldown(self._rob_cooldowns, ctx.author.id)
        if retry_after > 0:
            return await self._send_cooldown_embed(ctx, retry_after)

        if member.id == ctx.author.id:
            embed = discord.Embed(
                title="❌ Nice Try!",
                description="You can't rob yourself. That's just moving money between your own pockets!",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        if member.bot:
            embed = discord.Embed(
                title="❌ Target Protected",
                description="Bots are immune to robbery attempts!",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        # 1. Check required tools
        lockpicks = await EconomyDB.get_item_count(ctx.author.id, "lockpick")
        master_keys = await EconomyDB.get_item_count(ctx.author.id, "master_key")

        if lockpicks <= 0 and master_keys <= 0:
            embed = discord.Embed(
                title="🧰 Missing Tools",
                description="You need a **Lockpick** or a **Master Key** in your inventory to attempt a robbery! Grab one from `$shop`.",
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        # 2. Check victim data
        victim_data = await EconomyDB.get_user(member.id)
        victim_nodes = victim_data.get("nodes", 0) if victim_data else 0

        if not victim_data or victim_nodes < 200:
            embed = discord.Embed(
                title="💸 Not Worth It",
                description=(
                    f"Requested by {ctx.author.mention} attempting to steal from {member.mention}\n\n"
                    f"**{member.display_name}** doesn't have enough active nodes in their wallet (`< 200 Nodes`) to risk robbing them."
                ),
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        # 3. Real attack starts here -> lock in the cooldown and consume tool
        self._rob_cooldowns[ctx.author.id] = time.time() + ROB_COOLDOWN_SECONDS

        if master_keys > 0:
            await EconomyDB.remove_item(ctx.author.id, "master_key", 1)
            used_master_key = True
        else:
            await EconomyDB.remove_item(ctx.author.id, "lockpick", 1)
            used_master_key = False

        # 4. Calculate Odds vs Protections
        victim_firewalls = await EconomyDB.get_item_count(member.id, "firewall")

        if used_master_key:
            success_rate = 100
        else:
            success_rate = 25
            if victim_firewalls > 0:
                success_rate -= 10

        roll = random.randint(1, 100)
        audit_line = f"Requested by {ctx.author.mention} attempting to steal from {member.mention}"

        opening_embed = discord.Embed(
            title="🥷 Sneaking In...",
            description=f"{audit_line}\n\nAttempting to bypass **{member.display_name}**'s security controls...",
            color=discord.Color.blurple()
        )
        opening_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        msg = await ctx.send(embed=opening_embed)
        await asyncio.sleep(2.0)

        if roll <= success_rate:
            stolen_percent = self._calculate_weighted_steal_percentage()

            malware_usb = await EconomyDB.get_item_count(ctx.author.id, "usb")
            if malware_usb > 0:
                stolen_percent = min(90, stolen_percent + 10)
                await EconomyDB.remove_item(ctx.author.id, "usb", 1)
                usb_note = "\n💾 *Your Malware USB amplified the overall payout!*"
            else:
                usb_note = ""

            amount = int(victim_nodes * (stolen_percent / 100))

            await EconomyDB.update_balance(
                user_id=ctx.author.id,
                nodes=amount,
                action_type="CRIME_ROB_SUCCESS",
                details=f"Robbed {member.id}"
            )
            await EconomyDB.update_balance(
                user_id=member.id,
                nodes=-amount,
                action_type="CRIME_ROB_VICTIM",
                details=f"Robbed by {ctx.author.id}"
            )

            success_embed = discord.Embed(
                title="🔓 Robbery Successful!",
                description=(
                    f"{audit_line}\n\n"
                    f"You successfully snagged **{stolen_percent}%** of {member.mention}'s wallet!\n\n"
                    f"💰 **Stolen:** `+{amount:,}` Nodes{usb_note}"
                ),
                color=discord.Color.green()
            )
            success_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await msg.edit(embed=success_embed)
        else:
            user_data = await EconomyDB.get_user(ctx.author.id)
            user_nodes = user_data.get("nodes", 0) if user_data else 0

            percentages = list(range(5, 21))
            weights = [100, 75, 55, 40, 30, 22, 16, 12, 9, 6, 4, 3, 2, 1.5, 1, 0.5]
            
            fine_percent = random.choices(percentages, weights=weights, k=1)[0]
            fine = int(user_nodes * (fine_percent / 100))
            fine = max(150, fine)

            await EconomyDB.update_balance(
                user_id=ctx.author.id,
                nodes=-fine,
                action_type="CRIME_ROB_FAIL",
                details=f"Failed robbing {member.id}"
            )

            firewall_break = ""
            if victim_firewalls > 0 and random.random() < 0.4:
                await EconomyDB.remove_item(member.id, "firewall", 1)
                firewall_break = "\n🛡️ *The target's Firewall was destroyed during the alert counter-strike!*"

            fail_embed = discord.Embed(
                title="🚨 Caught Red-Handed!",
                description=(
                    f"{audit_line}\n\n"
                    f"You got caught attempting to rob {member.mention}!\n\n"
                    f"💸 **Fine Paid:** You were penalized **{fine_percent}%** (`-{fine:,}` Nodes).{firewall_break}"
                ),
                color=discord.Color.red()
            )
            fail_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await msg.edit(embed=fail_embed)

    @commands.command(name="hack")
    async def hack_bank(self, ctx: commands.Context, member: discord.Member):
        """Launch a high-risk attack against a user's Bank Vault nodes."""
        retry_after = self._check_cooldown(self._hack_cooldowns, ctx.author.id)
        if retry_after > 0:
            return await self._send_cooldown_embed(ctx, retry_after)

        if member.id == ctx.author.id:
            embed = discord.Embed(
                title="❌ Invalid Target",
                description="You can't hack your own bank account!",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        if member.bot:
            embed = discord.Embed(
                title="❌ Access Denied",
                description="Bots don't have bank accounts you can target.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        # 1. Require Botnet
        botnets = await EconomyDB.get_item_count(ctx.author.id, "botnet")
        if botnets <= 0:
            embed = discord.Embed(
                title="💻 Hardware Required",
                description="Hacking a bank vault requires an active **Botnet Access** module. Buy one in `$shop`!",
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        victim_data = await EconomyDB.get_user(member.id)
        bank_nodes = victim_data.get("bank_nodes", victim_data.get("bank", 0)) if victim_data else 0

        if not victim_data or bank_nodes < 2000:
            embed = discord.Embed(
                title="🛡️ Vault Too Low",
                description=(
                    f"Requested by {ctx.author.mention} attempting to steal from {member.mention}\n\n"
                    f"**{member.display_name}** has less than `2,000` Nodes in their bank vault. It's not worth burning a Botnet for this target."
                ),
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            return await ctx.send(embed=embed)

        # 2. Real attack starts here -> lock in cooldown and burn Botnet
        self._hack_cooldowns[ctx.author.id] = time.time() + HACK_COOLDOWN_SECONDS
        await EconomyDB.remove_item(ctx.author.id, "botnet", 1)

        success_chance = 25
        roll = random.randint(1, 100)
        audit_line = f"Requested by {ctx.author.mention} attempting to steal from {member.mention}"

        opening_embed = discord.Embed(
            title="💻 Initiating System Hack...",
            description=f"{audit_line}\n\nDeploying botnet cluster to breach **{member.display_name}**'s bank vault...",
            color=discord.Color.purple()
        )
        opening_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        msg = await ctx.send(embed=opening_embed)
        await asyncio.sleep(3.5)

        if roll <= success_chance:
            stolen_percent = self._calculate_weighted_steal_percentage()
            amount = int(bank_nodes * (stolen_percent / 100))

            await EconomyDB.update_balance(
                user_id=member.id,
                bank=-amount,
                action_type="CRIME_HACK_VICTIM",
                details=f"Bank hacked by {ctx.author.id}"
            )
            await EconomyDB.update_balance(
                user_id=ctx.author.id,
                nodes=amount,
                action_type="CRIME_HACK_SUCCESS",
                details=f"Hacked bank of {member.id}"
            )

            success_embed = discord.Embed(
                title="👾 VAULT BREACHED!",
                description=(
                    f"{audit_line}\n\n"
                    f"Your botnet successfully breached **{member.mention}**'s vault and extracted **{stolen_percent}%** of their funds!\n\n"
                    f"💰 **Stolen:** `+{amount:,}` Nodes"
                ),
                color=discord.Color.green()
            )
            success_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await msg.edit(embed=success_embed)
        else:
            user_data = await EconomyDB.get_user(ctx.author.id)
            user_nodes = user_data.get("nodes", 0) if user_data else 0
            loss_fine = int(user_nodes * 0.15) if user_nodes > 1000 else 500

            await EconomyDB.update_balance(
                user_id=ctx.author.id,
                nodes=-loss_fine,
                action_type="CRIME_HACK_FAIL",
                details=f"Failed hack on {member.id}"
            )

            fail_embed = discord.Embed(
                title="⚡ HACK DEFLECTED!",
                description=(
                    f"{audit_line}\n\n"
                    f"The bank security fried your connection! Your Botnet was destroyed and you lost **`-{loss_fine:,}` Nodes** in damage penalties."
                ),
                color=discord.Color.red()
            )
            fail_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await msg.edit(embed=fail_embed)

    @rob_user.error
    @hack_bank.error
    async def crime_error_handler(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Target Missing",
                description=f"You need to specify a target user!\n\n**Usage:** `{ctx.prefix}{ctx.command.name} @user`",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

        elif isinstance(error, commands.MemberNotFound):
            embed = discord.Embed(
                title="❌ User Not Found",
                description="I couldn't find that user in this server grid.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(EconomyCrimes(bot))
