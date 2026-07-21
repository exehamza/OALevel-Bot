# import discord
# from discord.ext import commands
# import random
# from .database import EconomyDB

# # Global items ledger mapping IDs to properties
# ITEMS = {
#     # Protection
#     "firewall": {"name": "Firewall", "price": 5000, "emoji": "🛡️", "desc": "Reduces the chance of successful wallet robberies."},
#     "vault": {"name": "Bank Vault", "price": 25000, "emoji": "🗄️", "desc": "Protects your high-value nodes from robbery attempts."},
    
#     # Crime Hardware
#     "lockpick": {"name": "Lockpick", "price": 1500, "emoji": "🧰", "desc": "Required tool for initiating a wallet $rob."},
#     "botnet": {"name": "Botnet Access", "price": 7500, "emoji": "💻", "desc": "Required framework access point to perform a network $hack."},
#     "usb": {"name": "Malware USB", "price": 3500, "emoji": "💾", "desc": "Increases siphoned node yields during a successful robbery."},
#     "master_key": {"name": "Master Key", "price": 50000, "emoji": "🔑", "desc": "Guarantees absolute 100% bypass success on a single $rob vector."},

#     # Loot Crates & Keys
#     "loot_key": {"name": "Loot Box Key", "price": 1200, "emoji": "🗝️", "desc": "Encryption decryption key needed to unpack system cases."},
#     "common_case": {"name": "Common Case", "price": 2000, "emoji": "📦", "desc": "Contains standard data blocks and entry hardware."},
#     "rare_case": {"name": "Rare Case", "price": 7500, "emoji": "🔷", "desc": "Higher chance of mid-grade mining and attack modules."},
#     "epic_case": {"name": "Epic Case", "price": 20000, "emoji": "🔮", "desc": "Advanced casing containing high-end components."},
#     "legendary_case": {"name": "Legendary Case", "price": 65000, "emoji": "👑", "desc": "Top-tier container housing rare infrastructure items."},
    
#     # Mining Hardware
#     "node_miner": {"name": "Node Miner", "price": 10000, "emoji": "⛏️", "desc": "Generates +50 Nodes every hour passively."},
#     "gpu_rig": {"name": "GPU Rig", "price": 35000, "emoji": "🗲", "desc": "Generates +200 Nodes every hour passively."},
#     "ai_cluster": {"name": "AI Cluster", "price": 120000, "emoji": "🧠", "desc": "Generates +750 Nodes every hour passively."},
#     "quantum_server": {"name": "Quantum Server", "price": 500000, "emoji": "🪐", "desc": "Generates +3,500 Nodes every hour passively."},
# }

# # Loot Pool tables matching OhnePixel styles
# CASE_DROPS = {
#     "common_case": {
#         "items": ["nodes_500", "nodes_1000", "lockpick", "usb"],
#         "weights": [50, 25, 15, 10]
#     },
#     "rare_case": {
#         "items": ["nodes_2500", "lockpick", "usb", "firewall", "botnet"],
#         "weights": [40, 20, 15, 15, 10]
#     },
#     "epic_case": {
#         "items": ["nodes_8000", "firewall", "botnet", "vault", "loot_key"],
#         "weights": [35, 25, 20, 15, 5]
#     },
#     "legendary_case": {
#         "items": ["nodes_30000", "vault", "master_key", "founder_token", "dev_trophy"],
#         "weights": [40, 30, 20, 8, 2]
#     }
# }

# # Non-purchasable collectibles metadata
# COLLECTIBLES = {
#     "founder_token": {"name": "Founder Token", "emoji": "🪙", "desc": "Extremely rare cryptographic token indicating early network deployment."},
#     "dev_trophy": {"name": "Developer Trophy", "emoji": "🏆", "desc": "Mythical server relic awarded through extreme legendary luck."}
# }

# class EconomyShop(commands.Cog):
#     def __init__(self, bot):
#         self.bot = bot

#     @commands.command(name="shop")
#     async def view_shop(self, ctx):
#         """Browse available hardware and components in the network market."""
#         embed = discord.Embed(title="🛒 Deep-Web Hardware Marketplace", color=discord.Color.blue())
        
#         for item_id, info in ITEMS.items():
#             embed.add_field(
#                 name=f"{info['emoji']} {info['name']} — `{info['price']:,}` Nodes",
#                 value=f"└ *{info['desc']}*\n`ID: {item_id}`",
#                 inline=False
#             )
#         await ctx.send(embed=embed)

#     @commands.command(name="buy")
#     async def buy_item(self, ctx, item_id: str, quantity: int = 1):
#         """Purchase hardware modules from the marketplace."""
#         item_id = item_id.lower()
#         if item_id not in ITEMS:
#             return await ctx.send("❌ **Unknown Signature:** That item code does not exist in the marketplace layout.")
        
#         if quantity <= 0:
#             return await ctx.send("❌ **Invalid Packet:** Quantity must be 1 or higher.")

#         item = ITEMS[item_id]
#         total_cost = item["price"] * quantity

#         user_data = await EconomyDB.get_user(ctx.author.id)
#         if user_data["nodes"] < total_cost:
#             return await ctx.send(f"❌ **Transaction Timed Out:** Insufficient nodes. You need `{total_cost - user_data['nodes']:,}` more nodes.")

#         # Complete purchase transaction
#         await EconomyDB.update_balance(ctx.author.id, -total_cost, "SHOP_PURCHASE", f"Bought {quantity}x {item_id}")
#         await EconomyDB.add_item(ctx.author.id, item_id, quantity)

#         if item_id in ["node_miner", "gpu_rig", "ai_cluster", "quantum_server"]:
#             await EconomyDB.register_purchased_rig(ctx.author.id, item_id, quantity)

#         await ctx.send(f"🟩 **Transaction Confirmed!** Deployed `{quantity}x` **{item['name']}** into your inventory profile.")

#     @commands.command(name="inventory", aliases=["inv"])
#     async def view_inventory(self, ctx):
#         """View your currently deployed hardware blocks and inventory items."""
#         inv_data = await EconomyDB.get_full_inventory(ctx.author.id)
        
#         embed = discord.Embed(title=f"🎒 {ctx.author.display_name}'s Storage Bay Ledger", color=discord.Color.green())
#         embed.set_thumbnail(url=ctx.author.display_avatar.url)

#         if not inv_data:
#             embed.description = "*Storage bay empty. No hardware units detected.*"
#             return await ctx.send(embed=embed)

#         desc = ""
#         for item_id, qty in inv_data:
#             # Look up inside store ledger, fallback to collectibles if unique drop
#             item_info = ITEMS.get(item_id) or COLLECTIBLES.get(item_id)
#             if item_info:
#                 desc += f"{item_info['emoji']} **{item_info['name']}** ×`{qty}`\n└ *{item_info['desc']}*\n\n"
#             else:
#                 desc += f"❓ `UNKNOWN_ITEM_ID: {item_id}` ×`{qty}`\n\n"

#         embed.description = desc
#         await ctx.send(embed=embed)

#     @commands.command(name="open")
#     async def open_case(self, ctx, case_id: str):
#         """Deconstruct encryption cases using your loot keys."""
#         case_id = case_id.lower()
#         if case_id not in CASE_DROPS:
#             return await ctx.send("❌ **Parsing Exception:** Specified asset is not an unpackable case structure.")

#         # Verify items availability
#         cases_owned = await EconomyDB.get_item_count(ctx.author.id, case_id)
#         keys_owned = await EconomyDB.get_item_count(ctx.author.id, "loot_key")

#         if cases_owned <= 0:
#             return await ctx.send(f"❌ **Missing Dependency:** Your inventory holds zero units of `{case_id}`.")
#         if keys_owned <= 0:
#             return await ctx.send("❌ **Decryption Lock:** Opening cases requires an active **Loot Box Key** (`$buy loot_key`).")

#         # Send initial message
#         msg = await ctx.send(f"🔓 **Key Accepted.** Running algorithmic brute-force decompression routine on `{case_id}`...")

#         # Use 'async with' so the bot types cleanly while executing the code inside it
#         async with ctx.typing():
#             # Strip components
#             await EconomyDB.remove_item(ctx.author.id, case_id, 1)
#             await EconomyDB.remove_item(ctx.author.id, "loot_key", 1)

#             # Unbox sequence mechanics
#             pool = CASE_DROPS[case_id]
#             reward_id = random.choices(pool["items"], weights=pool["weights"], k=1)[0]

#             # OPTIONAL: Add an artificial 2-second sleep if you want to emphasize the "brute force" suspense!
#             # import asyncio
#             # await asyncio.sleep(2)

#             # Check if the unboxed drop is raw Nodes vs an Item asset
#             if reward_id.startswith("nodes_"):
#                 node_payout = int(reward_id.split("_")[1])
#                 await EconomyDB.update_balance(ctx.author.id, node_payout, "CASE_UNBOX_NODES", f"Unboxed {node_payout} nodes from {case_id}")
                
#                 await msg.edit(content=f"✨ **Decompression Finished!** The crate cracked open and revealed a raw cache bundle of **`+{node_payout:,}` Nodes**!")
#             else:
#                 # Hand over item or collectible asset
#                 await EconomyDB.add_item(ctx.author.id, reward_id, 1)
#                 item_data = ITEMS.get(reward_id) or COLLECTIBLES.get(reward_id)
#                 name = item_data["name"] if item_data else reward_id
#                 emoji = item_data["emoji"] if item_data else "🎁"

#                 await msg.edit(content=f"⭐ **DECRYPTION COMPLETE!** You successfully rolled: \n➡️ {emoji} **{name}** — Added to your storage bay inventory ledger!")
    
#     @commands.command(name="deposit", aliases=["dep"])
#     async def deposit_nodes(self, ctx, amount: str):
#         """Transfer hot wallet nodes into your secure bank network."""
#         user_data = await EconomyDB.get_user(ctx.author.id)
#         wallet = user_data.get("nodes", 0)

#         # Process text shorthands for banking macros
#         if amount.lower() in ["all", "max"]:
#             transfer_amount = wallet
#         else:
#             try:
#                 transfer_amount = int(amount)
#             except ValueError:
#                 return await ctx.send("❌ **Parsing Error:** Please specify a valid integer number of nodes or use `all`.")

#         if transfer_amount <= 0:
#             return await ctx.send("❌ **Invalid Packet:** Deposit amount must be greater than zero.")

#         if wallet < transfer_amount:
#             return await ctx.send(f"❌ **Transaction Aborted:** Insufficient nodes in your active wallet. You only have `{wallet:,}` nodes.")

#         # update_balance deducts from wallet (nodes) and adds to bank (bank) in one single atomic transaction
#         await EconomyDB.update_balance(
#             user_id=ctx.author.id,
#             nodes=-transfer_amount,
#             bank=transfer_amount,
#             action_type="BANK_DEPOSIT",
#             details=f"Deposited {transfer_amount} nodes into secure core"
#         )
        
#         await ctx.send(f"📥 **Network Sync Complete:** Transferred `{transfer_amount:,}` Nodes into your secure bank vault partition.")

#     @commands.command(name="withdraw", aliases=["with"])
#     async def withdraw_nodes(self, ctx, amount: str):
#         """Retrieve secured nodes back into your active wallet layer."""
#         user_data = await EconomyDB.get_user(ctx.author.id)
#         bank = user_data.get("bank_nodes", 0)

#         if amount.lower() in ["all", "max"]:
#             transfer_amount = bank
#         else:
#             try:
#                 transfer_amount = int(amount)
#             except ValueError:
#                 return await ctx.send("❌ **Parsing Error:** Please specify a valid integer number of nodes or use `all`.")

#         if transfer_amount <= 0:
#             return await ctx.send("❌ **Invalid Packet:** Withdrawal amount must be greater than zero.")

#         if bank < transfer_amount:
#             return await ctx.send(f"❌ **Transaction Aborted:** Your secure bank partition only holds `{bank:,}` nodes.")

#         # Deducts from bank storage and returns currency directly back to wallet (nodes)
#         await EconomyDB.update_balance(
#             user_id=ctx.author.id,
#             nodes=transfer_amount,
#             bank=-transfer_amount,
#             action_type="BANK_WITHDRAWAL",
#             details=f"Withdrew {transfer_amount} nodes from secure core"
#         )
        
#         await ctx.send(f"📤 **Network Sync Complete:** Extracted `{transfer_amount:,}` Nodes back into your active hot wallet layer.")

# def setup(bot):
#     bot.add_cog(EconomyShop(bot))