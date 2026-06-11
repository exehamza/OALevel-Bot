import io
import math
import random
import sqlite3
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import discord
from discord.ext import commands
from config import Config

database = sqlite3.connect("database.sqlite")
cursor = database.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS levels (
    user_id INTEGER, 
    guild_id INTEGER, 
    exp INTEGER, 
    level INTEGER, 
    last_lvl INTEGER
)""")
database.commit()

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
            cursor.execute(
                "INSERT INTO levels (user_id, guild_id, exp, level, last_lvl) VALUES(?, ?, 0, 0, 0)",
                (message.author.id, message.guild.id)
            )
            database.commit()
        else:
            exp = result[2]
            lvl = result[3]
            last_lvl = result[4]
            
            exp_gained = 15
            exp += exp_gained
            lvl = 0.1 * (math.sqrt(exp))
            
            cursor.execute(
                "UPDATE levels SET exp = ?, level = ? WHERE user_id = ? AND guild_id = ?",
                (exp, lvl, message.author.id, message.guild.id)
            )
            database.commit()
            
            if int(lvl) > last_lvl:
                
                channel = self.bot.get_channel(Config.LEVEL_CHANNEL_ID)
                if channel is None:
                    channel = message.channel
                
                await channel.send(f"Congratulations {message.author.mention}, you leveled up to level {int(lvl)}!")
                
                cursor.execute(
                    "UPDATE levels SET last_lvl = ? WHERE user_id = ? AND guild_id = ?",
                    (int(lvl), message.author.id, message.guild.id)
                )
                database.commit()
    
    @commands.command(name="level", aliases=["rank"], description="Check your level or someone else's level")
    async def level(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        
        if target.bot:
            return await ctx.send("Bots do not have levels!")

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
            
        # math for xp
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
            return await ctx.send("⚠️ Error: System background assets are missing. Contact an Admin!")

        draw = ImageDraw.Draw(base_card)
        username = f"@{target.name}"
        
        try:
            font_username = ImageFont.truetype("arialbd.ttf", 35)
            font_metrics = ImageFont.truetype("arial.ttf", 25)
        except IOError:
            try:
                font_username = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
                font_metrics = ImageFont.truetype("DejaVuSans.ttf", 20)
            except IOError:
                font_username = ImageFont.load_default()
                font_metrics = ImageFont.load_default()

        if len(username) > 15:
            try:
                font_username_scaled = ImageFont.truetype("arialbd.ttf", 18)
            except IOError:
                try:
                    font_username_scaled = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
                except IOError:
                    font_username_scaled = ImageFont.load_default()
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

        # saving image in buffer
        final_buffer = io.BytesIO()
        base_card.save(final_buffer, format="PNG")
        final_buffer.seek(0)
        
        discord_file = discord.File(fp=final_buffer, filename=f"rank_{target.id}.png")
        await ctx.send(file=discord_file)

async def setup(bot):
    await bot.add_cog(Leveling(bot))