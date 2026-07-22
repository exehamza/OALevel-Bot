import discord
from discord.ext import commands
import random
import asyncio
from .database import EconomyDB

class BlackjackView(discord.ui.View):
    """Interactive Button Interface for Dark Web Blackjack."""
    def __init__(self, ctx, player_id, bet, player_hand, dealer_hand, tick_emoji, cross_emoji):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.player_id = player_id
        self.bet = bet
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.TICK = tick_emoji
        self.CROSS = cross_emoji
        self.deck = self.generate_deck()

    def generate_deck(self):
        suits = ['♠', '♥', '♦', '♣']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        return [f"{r}{s}" for r in ranks for s in suits]

    def calculate_value(self, hand):
        value = 0
        aces = 0
        for card in hand:
            rank = card[:-1]
            if rank in ['J', 'Q', 'K']:
                value += 10
            elif rank == 'A':
                aces += 1
                value += 11
            else:
                value += int(rank)
        
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    def make_embed(self, dealer_hidden=True):
        p_val = self.calculate_value(self.player_hand)
        
        if dealer_hidden:
            d_cards = f"`[{self.dealer_hand[0]}]` `[??]`"
            d_val = "??"
        else:
            d_cards = " ".join([f"`[{c}]`" for c in self.dealer_hand])
            d_val = str(self.calculate_value(self.dealer_hand))

        p_cards = " ".join([f"`[{c}]`" for c in self.player_hand])

        embed = discord.Embed(title="🃏 Darknet Blackjack Session", color=discord.Color.purple())
        embed.add_field(name="Dealer's Rig", value=f"Cards: {d_cards}\nValue: `{d_val}`", inline=False)
        embed.add_field(name="Your Mainframe", value=f"Cards: {p_cards}\nValue: `{p_val}`", inline=False)
        embed.set_footer(
            text=f"Total Stakes: {self.bet:,} Nodes | Requested by {self.ctx.author.name}", 
            icon_url=self.ctx.author.display_avatar.url
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            embed = discord.Embed(
                title=f"{self.CROSS} Access Denied",
                description="This is not your terminal session.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Hit (Request Packet)", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        card = random.choice(self.deck)
        self.player_hand.append(card)
        p_val = self.calculate_value(self.player_hand)

        if p_val > 21:
            self.stop()
            await EconomyDB.update_balance(self.player_id, -self.bet, "GAMBLE_LOSS", f"Lost {self.bet} nodes in Blackjack (Bust)")
            embed = self.make_embed(dealer_hidden=False)
            embed.description = f"{self.CROSS} **System Overflow (Bust)!** Your values exceeded 21. You lost `{self.bet:,}` Nodes."
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="Stand (Execute)", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer()
        
        # Dealer routine
        while self.calculate_value(self.dealer_hand) < 17:
            self.dealer_hand.append(random.choice(self.deck))

        p_val = self.calculate_value(self.player_hand)
        d_val = self.calculate_value(self.dealer_hand)
        
        embed = self.make_embed(dealer_hidden=False)

        if d_val > 21:
            await EconomyDB.update_balance(self.player_id, self.bet, "GAMBLE_WIN", f"Won {self.bet} nodes in Blackjack (Dealer Bust)")
            embed.description = f"{self.TICK} **Dealer System Crash!** The dealer bust with `{d_val}`. You won `+{self.bet:,}` Nodes!"
        elif p_val > d_val:
            await EconomyDB.update_balance(self.player_id, self.bet, "GAMBLE_WIN", f"Won {self.bet} nodes in Blackjack")
            embed.description = f"{self.TICK} **Breach Successful!** `{p_val}` beats `{d_val}`. You won `+{self.bet:,}` Nodes!"
        elif p_val < d_val:
            await EconomyDB.update_balance(self.player_id, -self.bet, "GAMBLE_LOSS", f"Lost {self.bet} nodes in Blackjack")
            embed.description = f"{self.CROSS} **Counter-Hacked!** Dealer's `{d_val}` beats your `{p_val}`. You lost `{self.bet:,}` Nodes."
        else:
            embed.description = f"🟨 **Packet Collision (Push).** Both nodes returned `{p_val}`. Your stakes were refunded."

        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=None)


class EconomyGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Custom Emojis
        self.TICK = "<:Tick:1514986183489360087>"
        self.CROSS = "<a:Cross:1514986232294281426>"

    async def pre_bet_check(self, ctx, bet: int):
        """Helper to check validity of bets."""
        if bet <= 0:
            embed = discord.Embed(
                title=f"{self.CROSS} Invalid Calculation",
                description="Submitting a null or negative calculation packet is invalid.",
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
    async def coin_flip(self, ctx, bet: int):
        """Flip a cryptographic coin for a 50/50 return or loss."""
        if not await self.pre_bet_check(ctx, bet):
            return

        outcome = random.choice(["heads", "tails"])
        
        # Simulating rolling matrix animation
        loading_embed = discord.Embed(
            title="🎲 Processing Transaction",
            description="*Running hashing calculation...*",
            color=discord.Color.blue()
        )
        loading_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        msg = await ctx.send(embed=loading_embed)
        await asyncio.sleep(1.2)

        if outcome == "heads":
            await EconomyDB.update_balance(ctx.author.id, bet, "GAMBLE_WIN", f"Coinflip win: {bet} nodes")
            result_embed = discord.Embed(
                title=f"{self.TICK} Binary Flip Success (Heads)!",
                description=f"Your predictive code compiled. Transferred `+{bet:,}` Nodes to your wallet.",
                color=discord.Color.green()
            )
        else:
            await EconomyDB.update_balance(ctx.author.id, -bet, "GAMBLE_LOSS", f"Coinflip loss: {bet} nodes")
            result_embed = discord.Embed(
                title=f"{self.CROSS} Binary Flip Corrupted (Tails)!",
                description=f"The sequence folded against you. Erased `-{bet:,}` Nodes.",
                color=discord.Color.red()
            )

        result_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await msg.edit(embed=result_embed)

    @commands.command(name="slots")
    async def slots(self, ctx, bet: int):
        """Play the high-variance proxy slot matrix machine."""
        if not await self.pre_bet_check(ctx, bet):
            return

        emojis = ["💾", "💻", "📟", "🔋", "🛡️", "💎"]
        reel1, reel2, reel3 = random.choice(emojis), random.choice(emojis), random.choice(emojis)
        
        loading_embed = discord.Embed(
            title="🎰 Matrix Initializing",
            description="*Spinning proxy encryption matrices...*",
            color=discord.Color.blue()
        )
        loading_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        msg = await ctx.send(embed=loading_embed)
        await asyncio.sleep(1.5)

        display_grid = f"┃ {reel1} ┃ {reel2} ┃ {reel3} ┃"

        if reel1 == reel2 == reel3:
            payout = bet * 5
            await EconomyDB.update_balance(ctx.author.id, payout, "GAMBLE_WIN", f"Slots Triple: {payout} nodes")
            result_embed = discord.Embed(
                title=f"{self.TICK} TRIPLE OVERWRITE!",
                description=f"{display_grid}\n\nFull code match. Payout multiplier `5x` processed: `+{payout:,}` Nodes!",
                color=discord.Color.green()
            )
        elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
            payout = int(bet * 1.5)
            await EconomyDB.update_balance(ctx.author.id, payout, "GAMBLE_WIN", f"Slots Double: {payout} nodes")
            result_embed = discord.Embed(
                title=f"{self.TICK} Partial Protocol Match",
                description=f"{display_grid}\n\nPayout multiplier `1.5x` processed: `+{payout:,}` Nodes.",
                color=discord.Color.green()
            )
        else:
            await EconomyDB.update_balance(ctx.author.id, -bet, "GAMBLE_LOSS", f"Slots loss: {bet} nodes")
            result_embed = discord.Embed(
                title=f"{self.CROSS} No Connection Matches",
                description=f"{display_grid}\n\nNode compilation failed. Lost `-{bet:,}` Nodes.",
                color=discord.Color.red()
            )

        result_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        await msg.edit(embed=result_embed)

    # @commands.command(name="roulette")
    # async def roulette(self, ctx, bet: int, choice: str):
    #     """Bet on a black, red, or zero routing node."""
    #     if not await self.pre_bet_check(ctx, bet):
    #         return

    #     choice = choice.lower()
    #     if choice not in ["red", "black", "zero"]:
    #         embed = discord.Embed(
    #             title=f"{self.CROSS} Syntax Error",
    #             description="Specify a routing quadrant target: `red`, `black`, or `zero`.",
    #             color=discord.Color.red()
    #         )
    #         embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
    #         return await ctx.send(embed=embed)

    #     spin_val = random.randint(0, 36)
    #     if spin_val == 0:
    #         landed = "zero"
    #     elif spin_val % 2 == 0:
    #         landed = "black"
    #     else:
    #         landed = "red"

    #     loading_embed = discord.Embed(
    #         title="🟢 Routing Sequence",
    #         description="*Dropping sequence routing ball onto sector...*",
    #         color=discord.Color.blue()
    #     )
    #     loading_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
    #     msg = await ctx.send(embed=loading_embed)
    #     await asyncio.sleep(1.5)

    #     if choice == landed:
    #         multiplier = 35 if landed == "zero" else 1
    #         winnings = bet * multiplier
    #         await EconomyDB.update_balance(ctx.author.id, winnings, "GAMBLE_WIN", f"Roulette win on {landed}")
    #         result_embed = discord.Embed(
    #             title=f"{self.TICK} Vector Traced!",
    #             description=f"Data packet dropped on Sector `{spin_val} ({landed.upper()})`!\nWon `+{winnings:,}` Nodes.",
    #             color=discord.Color.green()
    #         )
    #     else:
    #         await EconomyDB.update_balance(ctx.author.id, -bet, "GAMBLE_LOSS", f"Roulette loss on {landed}")
    #         result_embed = discord.Embed(
    #             title=f"{self.CROSS} Misrouted Packet",
    #             description=f"Packet misrouted to Sector `{spin_val} ({landed.upper()})`.\nData scrubbing initiated. Lost `-{bet:,}` Nodes.",
    #             color=discord.Color.red()
    #         )

    #     result_embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
    #     await msg.edit(embed=result_embed)

    # @commands.command(name="blackjack", aliases=["bj"])
    # async def blackjack(self, ctx, bet: int):
    #     """Launch an isolated blackjack gambling engine instance."""
    #     if not await self.pre_bet_check(ctx, bet):
    #         return

    #     deck = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    #     suits = ['♠', '♥', '♦', '♣']
    #     full_deck = [f"{r}{s}" for r in deck for s in suits]

    #     p_hand = [random.choice(full_deck), random.choice(full_deck)]
    #     d_hand = [random.choice(full_deck), random.choice(full_deck)]

    #     view = BlackjackView(ctx, ctx.author.id, bet, p_hand, d_hand, self.TICK, self.CROSS)
    #     embed = view.make_embed()
        
    #     if view.calculate_value(p_hand) == 21:
    #         bj_winnings = int(bet * 1.5)
    #         await EconomyDB.update_balance(ctx.author.id, bj_winnings, "GAMBLE_WIN", "Natural Blackjack")
    #         embed = view.make_embed(dealer_hidden=False)
    #         embed.description = f"{self.TICK} **NATURAL BACKDOOR EXPLOIT (Blackjack)!** You instantly hit 21. Collected `+{bj_winnings:,}` Nodes!"
    #         return await ctx.send(embed=embed)

    #     await ctx.send(embed=embed, view=view)

def setup(bot):
    bot.add_cog(EconomyGames(bot))