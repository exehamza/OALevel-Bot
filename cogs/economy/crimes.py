# import discord
# from discord.ext import commands
# import random
# import asyncio
# from .database import EconomyDB

# # rob
# # hack

# class EconomyCrimes(commands.Cog):
#     def __init__(self, bot):
#         self.bot = bot

#     @commands.command(name="rob")
#     @commands.cooldown(1, 3600, commands.BucketType.user) # 1 hour cooldown default
#     async def rob_user(self, ctx, member: discord.Member):
#         """Attempt to intercept node transfers from another user's wallet."""
#         if member.id == ctx.author.id:
#             ctx.command.reset_cooldown(ctx)
#             return await ctx.send("❌ **Loop Error:** Attempting to tap your own network profile creates a packet loop.")

#         # 1. Check if the attacker has a Lockpick
#         lockpicks = await EconomyDB.get_item_count(ctx.author.id, "lockpick")
#         master_keys = await EconomyDB.get_item_count(ctx.author.id, "master_key")
        
#         if lockpicks <= 0 and master_keys <= 0:
#             ctx.command.reset_cooldown(ctx)
#             return await ctx.send("❌ **Access Denied:** You need a **Lockpick** or **Master Key** in your inventory to bypass local wallet security.")

#         # 2. Check victim data
#         victim_data = await EconomyDB.get_user(member.id)
#         if not victim_data or victim_data["nodes"] < 200:
#             ctx.command.reset_cooldown(ctx)
#             return await ctx.send(f"❌ **Abort:** {member.display_name}'s mainframe does not hold enough active nodes (`< 200`) to justify the signature trace.")

#         # 3. Calculate Base Odds vs Protections
#         success_rate = 50  # Base 50% success
        
#         victim_firewalls = await EconomyDB.get_item_count(member.id, "firewall")
#         if victim_firewalls > 0:
#             success_rate -= 25 # Drop success rate down significantly
            
#         if master_keys > 0:
#             success_rate = 100 # Guaranteed match override

#         # Roll the dice
#         roll = random.randint(1, 100)
        
#         # Consume item used
#         if master_keys > 0:
#             await EconomyDB.remove_item(ctx.author.id, "master_key")
#         else:
#             await EconomyDB.remove_item(ctx.author.id, "lockpick")

#         msg = await ctx.send(f"📡 **Splitting packets...** Injecting security override protocols into {member.mention}'s proxy gateway...")
#         await asyncio.sleep(2.0)

#         if roll <= success_rate:
#             # Success! Steal a random portion of their current wallet nodes (10% to 35%)
#             stolen_percent = random.randint(10, 35)
            
#             # Boost via Malware USB if they have one
#             malware_usb = await EconomyDB.get_item_count(ctx.author.id, "usb")
#             if malware_usb > 0:
#                 stolen_percent += 15
#                 await EconomyDB.remove_item(ctx.author.id, "usb")
#                 usb_note = " *(Malware USB Amplified)*"
#             else:
#                 usb_note = ""

#             amount = int(victim_data["nodes"] * (stolen_percent / 100))
            
#             # Perform balances mutations
#             await EconomyDB.update_balance(ctx.author.id, amount, "CRIME_ROB_SUCCESS", f"Robbed {member.id}")
#             await EconomyDB.update_balance(member.id, -amount, "CRIME_ROB_VICTIM", f"Robbed by {ctx.author.id}")
            
#             await msg.edit(content=f"🔓 **Breach Confirmed!** You successfully intercepted their network payload.{usb_note}\nSiphoned `+{amount:,}` Nodes directly into your systems.")
#         else:
#             # Failure! Fined a portion of your own nodes or given to victim
#             fine = random.randint(150, 500)
#             await EconomyDB.update_balance(ctx.author.id, -fine, "CRIME_ROB_FAIL", f"Failed robbing {member.id}")
            
#             # Check for Firewall break triggers
#             firewall_break = ""
#             if victim_firewalls > 0 and random.random() < 0.4: # 40% chance firewall burns out protecting them
#                 await EconomyDB.remove_item(member.id, "firewall")
#                 firewall_break = "\n🛡️ *The target's Firewall hardware burned out during the trace counterattack.*"

#             await msg.edit(content=f"🚨 **Trace Detected!** {member.mention}'s countermeasures locked down your routing channel. You were fined `-{fine:,}` Nodes to clear your proxy logs.{firewall_break}")

#     @commands.command(name="hack")
#     @commands.cooldown(1, 14400, commands.BucketType.user) # 4 hour high-tier cooldown
#     async def hack_bank(self, ctx, member: discord.Member):
#         """Launch a high-risk system-wide payload extraction against a user's Bank Vault nodes."""
#         if member.id == ctx.author.id:
#             ctx.command.reset_cooldown(ctx)
#             return await ctx.send("❌ Can't hack your own grid infrastructure.")

#         # 1. Require high tier tool
#         botnets = await EconomyDB.get_item_count(ctx.author.id, "botnet")
#         if botnets <= 0:
#             ctx.command.reset_cooldown(ctx)
#             return await ctx.send("❌ **Hardware Exception:** Initiating a mainframe hijack requires active **Botnet Access**.")

#         victim_data = await EconomyDB.get_user(member.id)
#         if not victim_data or victim_data["bank_nodes"] < 2000:
#             ctx.command.reset_cooldown(ctx)
#             return await ctx.send("❌ **Target secure:** This user's bank configuration contains negligible node density. Not worth the botnet load.")

#         # Burn the tool access point
#         await EconomyDB.remove_item(ctx.author.id, "botnet")

#         # 20% flat chance for high tier bank rob payout
#         success_chance = 20
#         roll = random.randint(1, 100)

#         msg = await ctx.send(f"☠️ **CRITICAL ATTACK:** Directing Botnet clusters to saturate {member.mention}'s secure sub-layers...")
#         await asyncio.sleep(3.5)

#         if roll <= success_chance:
#             # Huge payout - siphons up to 40% of their BANK storage nodes
#             stolen_percent = random.randint(20, 40)
#             amount = int(victim_data["bank_nodes"] * (stolen_percent / 100))
            
#             # Unified through your existing EconomyDB helper architecture to update bank values
#             # and produce an audit log inside economy.db
#             await EconomyDB.update_bank_balance(member.id, -amount, "CRIME_HACK_VICTIM", f"Bank hacked by {ctx.author.id}")
#             await EconomyDB.update_balance(ctx.author.id, amount, "CRIME_HACK_SUCCESS", f"Hacked bank of {member.id}")

#             await msg.edit(content=f"🛸 **MAINFRAME COMPROMISED!** The botnet cracked their hardware array. Routed `+{amount:,}` Vaulted Nodes out of their storage grid!")
#         else:
#             # Fail punishment is steep
#             user_data = await EconomyDB.get_user(ctx.author.id)
#             user_nodes = user_data["nodes"] if user_data else 0
#             loss_fine = int(user_nodes * 0.15) if user_nodes > 1000 else 500
            
#             await EconomyDB.update_balance(ctx.author.id, -loss_fine, "CRIME_HACK_FAIL", f"Failed hack on {member.id}")
#             await msg.edit(content=f"⚡ **DEFENSE INTRUSION EXCLUSION:** The mainframe countered your vectors completely. Your botnet was vaporized and your systems short-circuited for `-{loss_fine:,}` Nodes.")

#     @rob_user.error
#     @hack_bank.error
#     async def crime_error_handler(self, ctx, error):
#         if isinstance(error, commands.CommandOnCooldown):
#             minutes, seconds = divmod(int(error.retry_after), 60)
#             hours, minutes = divmod(minutes, 60)
#             time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m {seconds}s"
#             await ctx.send(f"⏳ **System Interlock:** Your proxy channels are too hot. Wait **{time_str}** before launching another assault.")
#         elif isinstance(error, commands.MissingRequiredArgument):
#             await ctx.send(f"❌ **Target Unspecified:** Correct vector format: `{ctx.prefix}{ctx.command.name} @user`")

# def setup(bot):
#     bot.add_cog(EconomyCrimes(bot))