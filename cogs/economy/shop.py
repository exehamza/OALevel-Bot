import random
import asyncio
import discord
from discord.ext import commands
from .database import EconomyDB

# Global items ledger mapping IDs to properties
ITEMS = {
    # Protection
    "firewall": {"name": "Firewall", "price": 50_000, "emoji": "🛡️", "desc": "Reduces the chance of getting robbed."},

    # Crime Hardware
    "lockpick": {"name": "Lockpick", "price": 15_000, "emoji": "🧰", "desc": "Required tool to attempt a robbery."},
    "botnet": {"name": "Botnet Access", "price": 75_000, "emoji": "💻", "desc": "Required framework access to perform a network hack."},
    "usb": {"name": "Malware USB", "price": 35_000, "emoji": "💾", "desc": "Boosts your payout when successfully robbing someone."},
    "master_key": {"name": "Master Key", "price": 500_000, "emoji": "🔑", "desc": "Guarantees 100% success on a single robbery attempt."},

    # Special Drops
    "nitro_basic": {"name": "Discord Nitro Basic", "price": 0, "emoji": "🚀", "desc": "Redeemable 1-Month Discord Nitro Basic code!"},

    # Loot Crates & Keys
    "loot_key": {"name": "Loot Box Key", "price": 120_000, "emoji": "🗝️", "desc": "Key required to open any loot case."},
    "common_case": {"name": "Common Case", "price": 250_000, "emoji": "📦", "desc": "Contains basic items and node drops."},
    "rare_case": {"name": "Rare Case", "price": 750_000, "emoji": "🔷", "desc": "Better chance at mid-tier tools and node rewards."},
    "epic_case": {"name": "Epic Case", "price": 2_000_000, "emoji": "🔮", "desc": "High-tier crate with rare items and huge node pools."},
    "legendary_case": {"name": "Legendary Case", "price": 6_500_000, "emoji": "👑", "desc": "The ultimate crate. Features massive rewards and rare drops!"},
}

# Loot Pool tables
CASE_DROPS = {
    "common_case": {
        "items": [
            {"type": "item", "id": "lockpick", "amount": 1},
            {"type": "item", "id": "usb", "amount": 1},
            {"type": "nodes", "amount": 200_000},
            {"type": "nodes", "amount": 450_000},
        ],
        "weights": [50, 25, 15, 10]
    },
    "rare_case": {
        "items": [
            {"type": "item", "id": "firewall", "amount": 1},
            {"type": "item", "id": "botnet", "amount": 1},
            {"type": "item", "id": "usb", "amount": 2},
            {"type": "nodes", "amount": 600_000},
            {"type": "nodes", "amount": 1_200_000},
        ],
        "weights": [40, 20, 15, 15, 10]
    },
    "epic_case": {
        "items": [
            {"type": "item", "id": "botnet", "amount": 2},
            {"type": "item", "id": "firewall", "amount": 3},
            {"type": "nodes", "amount": 1_500_000},
            {"type": "nodes", "amount": 3_000_000},
            {"type": "item", "id": "master_key", "amount": 1},
        ],
        "weights": [35, 25, 20, 15, 5]
    },
    "legendary_case": {
        "items": [
            {"type": "item", "id": "botnet", "amount": 5},
            {"type": "nodes", "amount": 4_500_000},
            {"type": "nodes", "amount": 8_500_000},
            {"type": "item", "id": "master_key", "amount": 2},
            {"type": "nodes", "amount": 10_000_000},
            {"type": "special", "id": "nitro_basic", "amount": 1},
        ],
        "weights": [40, 30, 20, 8, 1.99999, 0.00001]
    }
}


class EconomyShop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="shop")
    async def view_shop(self, ctx: commands.Context):
        """Browse available hardware and components in the marketplace."""
        embed = discord.Embed(
            title="🛒 Black Market Shop",
            description="Welcome! Browse available tools, keys, and crates below. Use `buy <item_id> [quantity]` to make a purchase.",
            color=discord.Color.blue()
        )

        for item_id, info in ITEMS.items():
            if info.get("price", 0) <= 0:
                continue

            embed.add_field(
                name=f"{info['emoji']} {info['name']} — `{info['price']:,}` Nodes",
                value=f"└ {info['desc']}\n`ID: {item_id}`",
                inline=False
            )
        embed.set_footer(text="Tip: Keep your nodes safe in the bank using $deposit!")
        await ctx.send(embed=embed)

    @commands.command(name="buy")
    async def buy_item(self, ctx: commands.Context, item_id: str, quantity: int = 1):
        """Purchase hardware modules from the marketplace."""
        item_id = item_id.lower()

        if item_id not in ITEMS or ITEMS[item_id].get("price", 0) <= 0:
            embed = discord.Embed(
                title="❌ Item Not Found",
                description=f"I couldn't find an item with the ID `{item_id}` in the shop. Check `$shop` for valid items!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if quantity <= 0:
            embed = discord.Embed(
                title="❌ Invalid Quantity",
                description="Please enter a valid quantity of 1 or more.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        item = ITEMS[item_id]
        total_cost = item["price"] * quantity

        user_data = await EconomyDB.get_user(ctx.author.id)
        current_nodes = user_data.get("nodes", 0) if user_data else 0

        if current_nodes < total_cost:
            missing = total_cost - current_nodes
            embed = discord.Embed(
                title="💸 Insufficient Funds",
                description=f"You don't have enough nodes to complete this purchase!\n\n**Total Cost:** `{total_cost:,}` Nodes\n**You Need:** `{missing:,}` more Nodes",
                color=discord.Color.gold()
            )
            return await ctx.send(embed=embed)

        # Complete purchase transaction
        await EconomyDB.update_balance(
            user_id=ctx.author.id,
            nodes=-total_cost,
            action_type="SHOP_PURCHASE",
            details=f"Bought {quantity}x {item_id}"
        )
        await EconomyDB.add_item(ctx.author.id, item_id, quantity)

        # Safe dynamic hook for mining rigs or custom hardware handlers
        if hasattr(EconomyDB, "register_purchased_rig") and item_id in ["node_miner", "gpu_rig", "ai_cluster", "quantum_server"]:
            await EconomyDB.register_purchased_rig(ctx.author.id, item_id, quantity)

        embed = discord.Embed(
            title="🎉 Purchase Successful!",
            description=f"You bought **{quantity}x {item['emoji']} {item['name']}** for `{total_cost:,}` Nodes.",
            color=discord.Color.green()
        )
        embed.set_footer(text="The item(s) have been added to your inventory ($inv).")
        await ctx.send(embed=embed)

    @commands.command(name="inventory", aliases=["inv"])
    async def view_inventory(self, ctx: commands.Context):
        """View your currently deployed hardware blocks and inventory items."""
        inv_data = await EconomyDB.get_full_inventory(ctx.author.id)

        embed = discord.Embed(
            title=f"🎒 {ctx.author.display_name}'s Inventory",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        if not inv_data:
            embed.description = "Your inventory is currently empty! Use `$shop` to buy items or crates."
            return await ctx.send(embed=embed)

        desc = ""
        for item_id, qty in inv_data:
            item_info = ITEMS.get(item_id)
            if item_info:
                desc += f"{item_info['emoji']} **{item_info['name']}** ×`{qty}`\n└ *{item_info['desc']}*\n\n"
            else:
                desc += f"❓ `{item_id}` ×`{qty}`\n\n"

        embed.description = desc
        await ctx.send(embed=embed)

    @commands.command(name="view", aliases=["viewcase", "inspect"])
    async def view_case(self, ctx: commands.Context, case_id: str):
        """Inspect the contents and possible drop items inside an encryption case."""
        case_id = case_id.lower()
        if case_id not in CASE_DROPS:
            embed = discord.Embed(
                title="❌ Invalid Crate",
                description="That doesn't seem to be a valid case ID. Check `$shop` to see available crates!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        case_info = ITEMS.get(case_id, {})
        case_name = case_info.get("name", case_id.replace("_", " ").title())
        case_emoji = case_info.get("emoji", "📦")

        embed = discord.Embed(
            title=f"{case_emoji} Case Inspection: {case_name}",
            description="Here are the potential drops you can get from opening this case:",
            color=discord.Color.purple()
        )

        pool = CASE_DROPS[case_id]["items"]
        item_entries = []

        for drop in pool:
            if drop["type"] == "nodes":
                item_entries.append(f"⚡ **`{drop['amount']:,}` Nodes** Cache")
            else:
                item_data = ITEMS.get(drop["id"])
                amount_str = f" x{drop['amount']}" if drop.get("amount", 1) > 1 else ""
                if item_data:
                    item_entries.append(f"{item_data['emoji']} **{item_data['name']}**{amount_str}")
                else:
                    item_entries.append(f"📦 **`{drop['id']}`**{amount_str}")

        embed.add_field(
            name="Possible Rewards",
            value="\n".join(f"• {entry}" for entry in item_entries),
            inline=False
        )
        embed.set_footer(text="Requires 1x Loot Box Key (🗝️) to unlock.")
        await ctx.send(embed=embed)

    @commands.command(name="open")
    async def open_case(self, ctx: commands.Context, case_id: str):
        """Deconstruct encryption cases using your loot keys."""
        case_id = case_id.lower()
        if case_id not in CASE_DROPS:
            embed = discord.Embed(
                title="❌ Unknown Case",
                description="That case doesn't exist! Make sure you typed the ID correctly.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        cases_owned = await EconomyDB.get_item_count(ctx.author.id, case_id)
        keys_owned = await EconomyDB.get_item_count(ctx.author.id, "loot_key")

        if cases_owned <= 0:
            embed = discord.Embed(
                title="📦 Missing Case",
                description=f"You don't own any **{case_id}** cases! Buy one in the `$shop` first.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if keys_owned <= 0:
            embed = discord.Embed(
                title="🗝️ Key Needed",
                description="You need a **Loot Box Key** to open this case! Grab one from the `$shop` (`$buy loot_key`).",
                color=discord.Color.gold()
            )
            return await ctx.send(embed=embed)

        # Opening animation embed
        opening_embed = discord.Embed(
            title="🔓 Unlocking Case...",
            description=f"Unlocking your **{case_id.replace('_', ' ').title()}** with a key...",
            color=discord.Color.blurple()
        )
        msg = await ctx.send(embed=opening_embed)

        async with ctx.typing():
            # Consume key and case
            await EconomyDB.remove_item(ctx.author.id, case_id, 1)
            await EconomyDB.remove_item(ctx.author.id, "loot_key", 1)

            await asyncio.sleep(1.5)  # Visual suspense delay

            pool = CASE_DROPS[case_id]
            reward = random.choices(pool["items"], weights=pool["weights"], k=1)[0]

            if reward["type"] == "nodes":
                node_payout = reward["amount"]
                await EconomyDB.update_balance(
                    user_id=ctx.author.id,
                    nodes=node_payout,
                    action_type="CASE_UNBOX_NODES",
                    details=f"Unboxed {node_payout} nodes from {case_id}"
                )
                result_embed = discord.Embed(
                    title="✨ Cash Reward!",
                    description=f"You opened the case and found a stash of **`+{node_payout:,}` Nodes**!",
                    color=discord.Color.green()
                )
                await msg.edit(embed=result_embed)

            elif reward["type"] == "special" and reward["id"] == "nitro_basic":
                await EconomyDB.add_item(ctx.author.id, "nitro_basic", reward.get("amount", 1))
                godroll_embed = discord.Embed(
                    title="🎉 GOD-ROLL UNLOCKED!",
                    description=(
                        f"Unbelievable luck! {ctx.author.mention} opened a **Legendary Case** and won **Discord Nitro Basic**! 🚀\n\n"
                        f"*The reward has been added to your inventory. Open a support ticket with an admin to claim your code!*"
                    ),
                    color=discord.Color.magenta()
                )
                await msg.edit(embed=godroll_embed)

            else:
                item_id = reward["id"]
                amount = reward.get("amount", 1)
                await EconomyDB.add_item(ctx.author.id, item_id, amount)

                item_data = ITEMS.get(item_id)
                name = item_data["name"] if item_data else item_id
                emoji = item_data["emoji"] if item_data else "🎁"

                result_embed = discord.Embed(
                    title="⭐ Item Drop!",
                    description=f"You unlocked:\n➡️ {emoji} **{name}** ×`{amount}`\n\n*Added straight to your inventory!*",
                    color=discord.Color.gold()
                )
                await msg.edit(embed=result_embed)

    @commands.command(name="deposit", aliases=["dep"])
    async def deposit_nodes(self, ctx: commands.Context, amount: str):
        """Transfer wallet nodes into your secure bank network."""
        user_data = await EconomyDB.get_user(ctx.author.id)
        wallet = user_data.get("nodes", 0) if user_data else 0

        if amount.lower() in ["all", "max"]:
            transfer_amount = wallet
        else:
            try:
                transfer_amount = int(amount)
            except ValueError:
                embed = discord.Embed(
                    title="❌ Invalid Amount",
                    description="Please specify a valid number of nodes or use `all`.",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)

        if transfer_amount <= 0:
            embed = discord.Embed(
                title="❌ Invalid Amount",
                description="You must deposit an amount greater than zero.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if wallet < transfer_amount:
            embed = discord.Embed(
                title="❌ Insufficient Wallet Balance",
                description=f"You don't have that many nodes in your wallet! Current wallet balance: `{wallet:,}` Nodes.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        await EconomyDB.update_balance(
            user_id=ctx.author.id,
            nodes=-transfer_amount,
            bank=transfer_amount,
            action_type="BANK_DEPOSIT",
            details=f"Deposited {transfer_amount} nodes into secure core"
        )

        embed = discord.Embed(
            title="📥 Deposit Successful",
            description=f"Successfully deposited `{transfer_amount:,}` Nodes into your bank vault.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Your bank balance is safe from robbers!")
        await ctx.send(embed=embed)

    @commands.command(name="withdraw", aliases=["with"])
    async def withdraw_nodes(self, ctx: commands.Context, amount: str):
        """Retrieve secured nodes back into your active wallet."""
        user_data = await EconomyDB.get_user(ctx.author.id)
        bank = user_data.get("bank_nodes", 0) if user_data else 0

        if amount.lower() in ["all", "max"]:
            transfer_amount = bank
        else:
            try:
                transfer_amount = int(amount)
            except ValueError:
                embed = discord.Embed(
                    title="❌ Invalid Amount",
                    description="Please specify a valid number of nodes or use `all`.",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)

        if transfer_amount <= 0:
            embed = discord.Embed(
                title="❌ Invalid Amount",
                description="You must withdraw an amount greater than zero.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if bank < transfer_amount:
            embed = discord.Embed(
                title="❌ Insufficient Bank Balance",
                description=f"You don't have that many nodes in your bank vault! Current bank balance: `{bank:,}` Nodes.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        await EconomyDB.update_balance(
            user_id=ctx.author.id,
            nodes=transfer_amount,
            bank=-transfer_amount,
            action_type="BANK_WITHDRAWAL",
            details=f"Withdrew {transfer_amount} nodes from secure core"
        )

        embed = discord.Embed(
            title="📤 Withdrawal Successful",
            description=f"Successfully withdrew `{transfer_amount:,}` Nodes back into your wallet.",
            color=discord.Color.green()
        )
        embed.set_footer(text="Watch out! Nodes in your wallet can be stolen.")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(EconomyShop(bot))