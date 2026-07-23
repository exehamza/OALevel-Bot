import io
import math
import os
import sqlite3
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import discord
from discord.ext import commands
from config import Config

# Step out from cogs/ into the main Discord Bot directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Define database path inside the root 'data' folder
DB_PATH = os.path.join(BASE_DIR, "data", "database.sqlite")

# Ensure the 'data' directory exists before connecting
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Connect to the SQLite database
database = sqlite3.connect(DB_PATH)
cursor = database.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS levels (
    user_id INTEGER, 
    guild_id INTEGER, 
    exp INTEGER, 
    level INTEGER, 
    last_lvl INTEGER
)""")
database.commit()

# --- HELPER FUNCTION TO SAFELY LOAD BUNDLED FONTS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Go up one level from 'cogs' to reach the main project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_font(filename, size):
    """Attempts to load a bundled font from the 'fonts' directory."""
    font_path = os.path.join(BASE_DIR, "fonts", filename)
    
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    else:
        print(f"[Font Warning] Could not find '{filename}' at path: {font_path}")
        try:
            return ImageFont.truetype(filename, size)
        except IOError:
            return ImageFont.load_default()


class Leveling(commands.Cog):
    
    def __init__(self, bot):
        self.bot = bot
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        cursor.execute(
            "SELECT user_id, guild_id, exp, level, last_lvl FROM levels WHERE user_id = ? AND guild_id = ?",
            (message.author.id, message.guild.id)
        )
        result = cursor.fetchone()
        
        if result is None:
            initial_exp = (15*1.25) if message.author.premium_since is not None else 10
            
            cursor.execute(
                "INSERT INTO levels (user_id, guild_id, exp, level, last_lvl) VALUES(?, ?, ?, 0, 0)",
                (message.author.id, message.guild.id, initial_exp)
            )
            database.commit()
        else:
            exp = result[2]
            lvl = result[3]
            last_lvl = result[4]
            
            exp_gained = 10
            
            if message.author.premium_since is not None:
                exp_gained = int(exp_gained * 1.25)
                
            exp += exp_gained
            lvl = 0.1 * (math.sqrt(exp))
            current_lvl_int = int(lvl)
            
            cursor.execute(
                "UPDATE levels SET exp = ?, level = ? WHERE user_id = ? AND guild_id = ?",
                (exp, lvl, message.author.id, message.guild.id)
            )
            database.commit()
            
            if current_lvl_int > last_lvl:
                channel = self.bot.get_channel(Config.LEVEL_CHANNEL_ID)
                if channel is None:
                    channel = message.channel
                
                await channel.send(f"Congratulations {message.author.mention}, you leveled up to level {current_lvl_int}!")
                
                cursor.execute(
                    "UPDATE levels SET last_lvl = ? WHERE user_id = ? AND guild_id = ?",
                    (current_lvl_int, message.author.id, message.guild.id)
                )
                database.commit()

                if current_lvl_int >= 10:
                    role = message.guild.get_role(Config.IMAGE_PERMS_ROLE_ID)
                    if role and role not in message.author.roles:
                        try:
                            await message.author.add_roles(role)
                            embed = discord.Embed(
                                description=f"<:Tick:1514986183489360087> {message.author.mention} has unlocked the **{role.name}** role for reaching Level 10!",
                                color=discord.Color.green()
                            )
                            await channel.send(embed=embed)
                        except discord.Forbidden:
                            print(f"[Leveling Error] Bot missing permissions to manage roles or role is higher than the bot's hierarchy.")
                        except discord.HTTPException:
                            print(f"[Leveling Error] Failed to update roles due to a network or API issue.")
    
    @commands.command(name="level", aliases=["rank"], description="Check your level or someone else's level")
    async def level(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        
        if target.bot:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> Bots do not have levels!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        rank = 1
        cursor.execute("SELECT user_id FROM levels WHERE guild_id = ? ORDER BY exp DESC", (ctx.guild.id,))
        result = cursor.fetchall()
        
        for i in range(len(result)):
            if result[i][0] == target.id:
                break
            rank += 1
            
        cursor.execute(
            "SELECT exp, level FROM levels WHERE user_id = ? AND guild_id = ?",
            (target.id, ctx.guild.id)
        )
        user_data = cursor.fetchone()
        
        if user_data is None:
            lifetime_exp, level = 0, 0
        else:
            lifetime_exp = user_data[0]
            level = int(user_data[1])
            
        xp_floor_current_lvl = int((level / 0.1) ** 2)
        xp_floor_next_lvl = int(((level + 1) / 0.1) ** 2)
        
        current_level_xp = lifetime_exp - xp_floor_current_lvl
        xp_needed_for_this_tier = xp_floor_next_lvl - xp_floor_current_lvl
        
        if current_level_xp < 0:
            current_level_xp = 0

        progress_ratio = min(current_level_xp / max(xp_needed_for_this_tier, 1), 1.0)
        
        try:
            base_card = Image.open("rank_card.png").convert("RGBA")
        except FileNotFoundError:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> Error: System background assets are missing. Contact an Admin!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        draw = ImageDraw.Draw(base_card)
        username = f"@{target.name}"
        
        # --- LOAD BUNDLED FONTS ---
        font_username = load_font("Arial-Bold.TTF", 35)
        font_metrics = load_font("Arial.TTF", 25)

        if len(username) > 15:
            font_username_scaled = load_font("Arial-Bold.TTF", 100)
            draw.text((150, 27), username, fill=(255, 255, 255, 255), font=font_username_scaled)
        else:
            draw.text((150, 27), username, fill=(255, 255, 255, 255), font=font_username)
        
        draw.text((155, 100), f"Level: {level}", fill=(255, 255, 255, 255), font=font_metrics)
        draw.text((270, 100), f"XP: {current_level_xp}/{xp_needed_for_this_tier}", fill=(200, 200, 200, 255), font=font_metrics)
        draw.text((444, 100), f"Rank: #{rank}", fill=(255, 215, 0, 255), font=font_metrics)

        bar_x, bar_y = 11, 150      
        max_width, bar_height = 629, 35
        radius = 12
        current_width = int(max_width * progress_ratio)
        
        if current_width > (radius * 2):
            fill_color = (229, 83, 74, 255)
            draw.rounded_rectangle(
                [bar_x, bar_y, bar_x + current_width, bar_y + bar_height],
                radius=radius,
                fill=fill_color
            )

        avatar_size = (100, 100)
        avatar_x = 71 - (avatar_size[0] // 2)
        avatar_y = 76 - (avatar_size[1] // 2)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(target.display_avatar.url) as response:
                    if response.status == 200:
                        avatar_bytes = await response.read()
                        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                        avatar = avatar.resize(avatar_size, Image.Resampling.LANCZOS)
                        
                        mask = Image.new("L", avatar_size, 0)
                        mask_draw = ImageDraw.Draw(mask)
                        mask_draw.ellipse((0, 0) + avatar_size, fill=255)
                        
                        base_card.paste(avatar, (avatar_x, avatar_y), mask=mask)
                    else:
                        raise Exception()
        except Exception:
            draw.ellipse(
                [avatar_x, avatar_y, avatar_x + avatar_size[0], avatar_y + avatar_size[1]],
                fill=(190, 190, 190, 255)
            )

        final_buffer = io.BytesIO()
        base_card.save(final_buffer, format="PNG")
        final_buffer.seek(0)
        
        discord_file = discord.File(fp=final_buffer, filename=f"rank_{target.id}.png")
        await ctx.send(file=discord_file)

    @commands.command(name="leaderboard", aliases=["lb"], description="Display the top server members")
    async def leaderboard(self, ctx):
        cursor.execute(
            "SELECT user_id, level, exp FROM levels WHERE guild_id = ? ORDER BY exp DESC LIMIT 10",
            (ctx.guild.id,)
        )
        top_entries = cursor.fetchall()

        if not top_entries:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> No data found for this server's leaderboard yet!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        row_w, row_h = 680, 72
        row_gap = 6
        total_height = len(top_entries) * (row_h + row_gap) - row_gap
        leaderboard_canvas = Image.new("RGBA", (row_w, total_height), (0, 0, 0, 0))

        X_RANK = 20
        X_AVATAR = 75
        X_NAME = 145
        X_STATS = 480
        CENTER_Y = row_h // 2

        font_rank = load_font("Arial-Bold.TTF", 26)
        font_name = load_font("Arial-Bold.TTF", 22)
        font_stats = load_font("Arial.TTF", 18)

        async with aiohttp.ClientSession() as session:
            for index, entry in enumerate(top_entries):
                user_id, level, exp = entry
                rank_num = index + 1

                try:
                    row_card = Image.open("lb_card.png").convert("RGBA")
                    if row_card.size != (row_w, row_h):
                        row_card = row_card.resize((row_w, row_h), Image.Resampling.LANCZOS)
                except FileNotFoundError:
                    row_card = Image.new("RGBA", (row_w, row_h), (32, 34, 37, 255))

                draw = ImageDraw.Draw(row_card)

                rank_text = f"#{rank_num}"
                rank_colors = [(255, 215, 0, 255), (170, 180, 195, 255), (205, 127, 50, 255)]
                rank_color = rank_colors[index] if index < 3 else (200, 200, 200, 255)
                draw.text((X_RANK, CENTER_Y - 16), rank_text, fill=rank_color, font=font_rank)

                member = ctx.guild.get_member(user_id)
                display_name = f"@{member.name}" if member else f"User_{str(user_id)[-4:]}"

                if len(display_name) > 18:
                    display_name = display_name[:15] + "..."
                draw.text((X_NAME, CENTER_Y - 14), display_name, fill=(255, 255, 255, 255), font=font_name)

                stats_text = f"Lvl {int(level)} • {exp:,} XP"
                draw.text((X_STATS, CENTER_Y - 11), stats_text, fill=(150, 155, 165, 255), font=font_stats)

                avatar_size = (50, 50)
                avatar_y = CENTER_Y - (avatar_size[1] // 2)
                avatar_pasted = False

                if member:
                    try:
                        async with session.get(member.display_avatar.url) as response:
                            if response.status == 200:
                                av_bytes = await response.read()
                                avatar_img = Image.open(io.BytesIO(av_bytes)).convert("RGBA")
                                resized_avatar = avatar_img.resize(avatar_size, Image.Resampling.LANCZOS)
                                
                                mask = Image.new("L", avatar_size, 0)
                                mask_draw = ImageDraw.Draw(mask)
                                mask_draw.ellipse((0, 0) + avatar_size, fill=255)
                                
                                row_card.paste(resized_avatar, (X_AVATAR, avatar_y), mask=mask)
                                avatar_pasted = True
                    except Exception:
                        pass

                if not avatar_pasted:
                    draw.ellipse([X_AVATAR, avatar_y, X_AVATAR + 50, avatar_y + 50], fill=(120, 125, 135, 255))

                y_position = index * (row_h + row_gap)
                leaderboard_canvas.paste(row_card, (0, y_position))

        final_buffer = io.BytesIO()
        leaderboard_canvas.save(final_buffer, format="PNG")
        final_buffer.seek(0)

        filename = "leaderboard.png"
        discord_file = discord.File(fp=final_buffer, filename=filename)

        embed = discord.Embed(
            title=f"🏆 {ctx.guild.name} Leaderboard",
            description="Here are the top active members in the server!",
            color=discord.Color.gold()
        )
        
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
            
        embed.set_image(url=f"attachment://{filename}")
        await ctx.send(file=discord_file, embed=embed)

    @commands.group(name="xp", invoke_without_command=True, description="Manage user XP settings")
    @commands.has_permissions(administrator=True)
    async def xp(self, ctx):
        embed = discord.Embed(
            description="<a:Cross:1514986232294281426> Incomplete statement. Use:\n`$xp add @user <amount>`\n`$xp remove @user <amount>`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @xp.command(name="add")
    @commands.has_permissions(administrator=True)
    async def xp_add(self, ctx, member: discord.Member, amount: int):
        if member.bot:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> You cannot modify XP for bots.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
            
        if amount <= 0:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> Please provide a positive number of XP to add.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        try:
            cursor.execute(
                "SELECT exp FROM levels WHERE user_id = ? AND guild_id = ?",
                (member.id, ctx.guild.id)
            )
            result = cursor.fetchone()

            if result is None:
                new_exp = amount
                new_lvl = 0.1 * (math.sqrt(new_exp))
                cursor.execute(
                    "INSERT INTO levels (user_id, guild_id, exp, level, last_lvl) VALUES(?, ?, ?, ?, ?)",
                    (member.id, ctx.guild.id, new_exp, new_lvl, int(new_lvl))
                )
            else:
                new_exp = result[0] + amount
                new_lvl = 0.1 * (math.sqrt(new_exp))
                cursor.execute(
                    "UPDATE levels SET exp = ?, level = ?, last_lvl = ? WHERE user_id = ? AND guild_id = ?",
                    (new_exp, new_lvl, int(new_lvl), member.id, ctx.guild.id)
                )
            database.commit()
        except sqlite3.Error as e:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> Database error: `{e}`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        
        if int(new_lvl) >= 10:
            role = ctx.guild.get_role(Config.IMAGE_PERMS_ROLE_ID)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role)
                except discord.Forbidden:
                    pass

        embed = discord.Embed(
            description=f"<:Tick:1514986183489360087> Added **{amount:,} XP** to {member.mention}.\nThey are now **Level {int(new_lvl)}** ({new_exp:,} Total XP).",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @xp.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def xp_remove(self, ctx, member: discord.Member, amount: int):
        if member.bot:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> Bots do not process tracking structures.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
            
        if amount <= 0:
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> Please provide a positive number of XP to subtract.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        try:
            cursor.execute(
                "SELECT exp FROM levels WHERE user_id = ? AND guild_id = ?",
                (member.id, ctx.guild.id)
            )
            result = cursor.fetchone()

            if result is None or result[0] <= 0:
                embed = discord.Embed(
                    description=f"<a:Cross:1514986232294281426> {member.mention} has no experience points to remove.",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)

            new_exp = max(0, result[0] - amount)
            new_lvl = 0.1 * (math.sqrt(new_exp))

            cursor.execute(
                "UPDATE levels SET exp = ?, level = ?, last_lvl = ? WHERE user_id = ? AND guild_id = ?",
                (new_exp, new_lvl, int(new_lvl), member.id, ctx.guild.id)
            )
            database.commit()
        except sqlite3.Error as e:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> Database error: `{e}`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        
        if int(new_lvl) < 10:
            role = ctx.guild.get_role(Config.IMAGE_PERMS_ROLE_ID)
            if role and role in member.roles:
                try:
                    await member.remove_roles(role)
                except discord.Forbidden:
                    pass

        embed = discord.Embed(
            description=f"<:Tick:1514986183489360087> Removed **{amount:,} XP** from {member.mention}.\nThey are now **Level {int(new_lvl)}** ({new_exp:,} Total XP).",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @xp.error
    async def xp_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> You need to be an **Administrator** to modify user experience values.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @xp_add.error
    async def xp_add_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> You need to be an **Administrator** to modify user experience values.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> Invalid Format. Usage: `$xp add @user <amount>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> An unexpected error occurred: `{error}`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @xp_remove.error
    async def xp_remove_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> You need to be an **Administrator** to modify user experience values.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            embed = discord.Embed(
                description="<a:Cross:1514986232294281426> Invalid Format. Usage: `$xp remove @user <amount>`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                description=f"<a:Cross:1514986232294281426> An unexpected error occurred: `{error}`",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Leveling(bot))