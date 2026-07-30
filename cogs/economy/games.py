import discord
from discord.ext import commands
import random
import asyncio
from typing import Union
from .database import EconomyDB

# Maximum allowable bet in Nodes
MAX_BET = 15_000_000
# Network tax on net profits (10%)
WINNING_TAX_RATE = 0.10

def not_in_thread():
    """Custom command check to block execution inside threads."""
    async def predicate(ctx):
        if isinstance(ctx.channel, discord.Thread):
            raise commands.CheckFailure("This command cannot be used inside threads.")
        return True
    return commands.check(predicate)

class EconomyGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Custom Emojis
        self.TICK = "<:Tick:1514986183489360087>"
        self.CROSS = "<a:Cross:1514986232294281426>"
        
    async def cog_check(self, ctx):
        # Exempt administrators from checking, or let them execute admin commands
        if ctx.author.guild_permissions.administrator:
            return True

        if await EconomyDB.is_blacklisted(ctx.author.id):
            await ctx.send("❌ You are blacklisted from using the network economy.")
            return False
        return True

    async def cog_command_error(self, ctx, error):
        """Cog-wide error handler to capture check failures (e.g. threads)."""
        if isinstance(error, commands.CheckFailure) and "threads" in str(error):
            embed = discord.Embed(
                description=f"{self.CROSS} This command cannot be used inside threads.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    async def resolve_bet_amount(self, ctx, bet_input: Union[int, str]) -> int | None:
        """Parses integer or 'all'/'max' inputs into a valid integer bet amount."""
        user_data = await EconomyDB.get_user(ctx.author.id)
        user_nodes = user_data["nodes"]

        if isinstance(bet_input, str):
            if bet_input.lower() in ["all", "max"]:
                if user_nodes <= 0:
                    embed = discord.Embed(
                        title=f"{self.CROSS} Insufficient Allocation",
                        description="You do not have any Nodes to place a bet.",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
                    await ctx.send(embed=embed)
                    return None
                
                # Cap 'all' at the max limit if user has more
                return min(user_nodes, MAX_BET)
            else:
                embed = discord.Embed(
                    title=f"{self.CROSS} Invalid Parameter",
                    description="Bet must be a positive integer or `all` / `max`.",
                    color=discord.Color.red()
                )
                embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
                await ctx.send(embed=embed)
                return None

        return bet_input

    async def pre_bet_check(self, ctx, bet: int) -> bool:
        """Helper to check validity of resolved bets."""
        if bet <= 0:
            embed = discord.Embed(
                title=f"{self.CROSS} Invalid Calculation",
                description="Submitting a null or negative calculation packet is invalid.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return False

        if bet > MAX_BET:
            embed = discord.Embed(
                title=f"{self.CROSS} Calculation Limit Exceeded",
                description=f"The maximum allowable gamble limit per operation is `{MAX_BET:,}` Nodes.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return False

        user_data = await EconomyDB.get_user(ctx.author.id)
        if user_data["nodes"] < bet:
            embed = discord.Embed(
                title=f"{self.CROSS} Insufficient Allocation",
                description=f"You lack `{bet - user_data['nodes']:,}` Nodes to clear this operation.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return False
            
        return True

    @commands.command(name="coinflip", aliases=["cf"])
    @not_in_thread()
    async def coin_flip(self, ctx, bet: Union[int, str]):
        """Flip a cryptographic coin for a 50/50 return or loss."""
        bet_amount = await self.resolve_bet_amount(ctx, bet)
        if bet_amount is None or not await self.pre_bet_check(ctx, bet_amount):
            return

        outcome = random.choice(["heads", "tails"])
        
        loading_embed = discord.Embed(
            title="🎲 Processing Transaction",
            description="*Running hashing calculation...*",
            color=discord.Color.blue()
        )
        loading_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        msg = await ctx.send(embed=loading_embed)
        await asyncio.sleep(1.2)

        if outcome == "heads":
            gross_profit = bet_amount
            tax_amount = int(gross_profit * WINNING_TAX_RATE)
            net_profit = gross_profit - tax_amount

            # Update wallet with net winnings
            await EconomyDB.update_balance(
                ctx.author.id, net_profit, "GAMBLE_WIN", f"Coinflip win: +{net_profit} nodes (Tax: {tax_amount})"
            )

            result_embed = discord.Embed(
                title=f"{self.TICK} Binary Flip Success (Heads)!",
                description=(
                    f"Your predictive code compiled successfully!\n\n"
                    f"• **Gross Winnings:** `+{gross_profit:,}` Nodes\n"
                    f"• **Network Tax (10%):** `-{tax_amount:,}` Nodes\n"
                    f"• **Net Transferred:** `+{net_profit:,}` Nodes"
                ),
                color=discord.Color.green()
            )
        else:
            await EconomyDB.update_balance(
                ctx.author.id, -bet_amount, "GAMBLE_LOSS", f"Coinflip loss: {bet_amount} nodes"
            )
            result_embed = discord.Embed(
                title=f"{self.CROSS} Binary Flip Corrupted (Tails)!",
                description=f"The sequence folded against you. Erased `-{bet_amount:,}` Nodes.",
                color=discord.Color.red()
            )

        result_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await msg.edit(embed=result_embed)

    @commands.command(name="slots")
    @not_in_thread()
    async def slots(self, ctx, bet: Union[int, str]):
        """Play the high-variance proxy slot matrix machine."""
        bet_amount = await self.resolve_bet_amount(ctx, bet)
        if bet_amount is None or not await self.pre_bet_check(ctx, bet_amount):
            return

        # Deduct initial bet upfront
        await EconomyDB.update_balance(
            ctx.author.id, -bet_amount, "GAMBLE_BET", f"Slots bet: {bet_amount} nodes"
        )

        emojis = ["💾", "💻", "📟", "🔋", "🛡️", "💎"]
        reel1, reel2, reel3 = (
            random.choice(emojis),
            random.choice(emojis),
            random.choice(emojis),
        )

        loading_embed = discord.Embed(
            title="🎰 Matrix Initializing",
            description="*Spinning proxy encryption matrices...*",
            color=discord.Color.blue(),
        )
        loading_embed.set_footer(
            text=f"Requested by {ctx.author.name}",
            icon_url=ctx.author.display_avatar.url,
        )
        msg = await ctx.send(embed=loading_embed)
        await asyncio.sleep(1.5)

        display_grid = f"┃ {reel1} ┃ {reel2} ┃ {reel3} ┃"

        if reel1 == reel2 == reel3:
            multiplier = 5.0
            gross_winnings = int(bet_amount * multiplier)
            tax_amount = int(gross_winnings * 0.10)
            net_winnings = gross_winnings - tax_amount
            
            # Refund initial bet + pay net winnings
            total_payout = bet_amount + net_winnings

            await EconomyDB.update_balance(
                ctx.author.id,
                total_payout,
                "GAMBLE_WIN",
                f"Slots Triple win: +{net_winnings} net nodes (Tax: {tax_amount})",
            )

            result_embed = discord.Embed(
                title=f"{self.TICK} TRIPLE OVERWRITE!",
                description=(
                    f"{display_grid}\n\n"
                    f"Full code match! Multiplier `5x` processed.\n\n"
                    f"• **Gross Winnings:** `+{gross_winnings:,}` Nodes\n"
                    f"• **Network Tax (10%):** `-{tax_amount:,}` Nodes\n"
                    f"• **Net Profit Added:** `+{net_winnings:,}` Nodes"
                ),
                color=discord.Color.green(),
            )

        elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
            multiplier = 1.5
            gross_winnings = int(bet_amount * multiplier)
            tax_amount = int(gross_winnings * 0.10)
            net_winnings = gross_winnings - tax_amount
            
            # Refund initial bet + pay net winnings
            total_payout = bet_amount + net_winnings

            await EconomyDB.update_balance(
                ctx.author.id,
                total_payout,
                "GAMBLE_WIN",
                f"Slots Double win: +{net_winnings} net nodes (Tax: {tax_amount})",
            )

            result_embed = discord.Embed(
                title=f"{self.TICK} Partial Protocol Match",
                description=(
                    f"{display_grid}\n\n"
                    f"Partial match! Multiplier `1.5x` processed.\n\n"
                    f"• **Gross Winnings:** `+{gross_winnings:,}` Nodes\n"
                    f"• **Network Tax (10%):** `-{tax_amount:,}` Nodes\n"
                    f"• **Net Profit Added:** `+{net_winnings:,}` Nodes"
                ),
                color=discord.Color.green(),
            )

        else:
            # Loss: Bet was already deducted upfront, just log the transaction
            await EconomyDB.log_transaction(
                ctx.author.id, "GAMBLE_LOSS", -bet_amount, f"Slots loss: {bet_amount} nodes"
            )

            result_embed = discord.Embed(
                title=f"{self.CROSS} No Connection Matches",
                description=(
                    f"{display_grid}\n\nNode compilation failed. Lost `-{bet_amount:,}` Nodes."
                ),
                color=discord.Color.red(),
            )

        result_embed.set_footer(
            text=f"Requested by {ctx.author.name}",
            icon_url=ctx.author.display_avatar.url,
        )
        await msg.edit(embed=result_embed)

async def setup(bot):
    await bot.add_cog(EconomyGames(bot))