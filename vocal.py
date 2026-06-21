import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TOKEN")
DATA_FILE = "vocal_data.json"

# ==================== INITIALISATION ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="=", intents=intents)

data = {
    "createurs": {},
    "owners": {},
    "pv_channels": {},
}

join_tracker = defaultdict(lambda: defaultdict(list))

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

load_data()

def is_createur(guild_id, user_id):
    return str(user_id) in data["createurs"].get(str(guild_id), [])

def is_owner(guild_id, user_id):
    return str(user_id) in data["owners"].get(str(guild_id), [])

def is_pv(guild_id, channel_id):
    return str(channel_id) in data["pv_channels"].get(str(guild_id), {})

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"✅ Vocal Bot connecté: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("------")

@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild
    guild_id = str(guild.id)
    user_id = str(member.id)

    # Quelqu'un rejoint une voc =pv
    if after.channel and is_pv(guild_id, str(after.channel.id)):
        channel_id = str(after.channel.id)
        pv_info = data["pv_channels"][guild_id][channel_id]
        whitelist = pv_info.get("whitelist", [])

        if not is_createur(guild_id, user_id) and str(user_id) not in whitelist:
            now = datetime.now()
            join_tracker[guild_id][user_id] = [
                t for t in join_tracker[guild_id][user_id]
                if (now - t).seconds < 30
            ]
            join_tracker[guild_id][user_id].append(now)

            try:
                await member.move_to(None)
            except:
                pass

            if len(join_tracker[guild_id][user_id]) >= 3:
                join_tracker[guild_id][user_id] = []
                try:
                    await member.timeout(timedelta(seconds=60), reason="Spam rejoindre une voc privée")
                    try:
                        await member.send("⛔ Tu as été expulsé 60 secondes pour avoir tenté de rejoindre une voc privée trop souvent.")
                    except:
                        pass
                except:
                    pass

    # Protection deco
    if before.channel and not after.channel:
        target_id = str(member.id)
        if is_createur(guild_id, target_id) or is_owner(guild_id, target_id):
            await asyncio.sleep(1)
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_disconnect):
                    if entry.target.id == member.id:
                        punisher = entry.user
                        punisher_id = str(punisher.id)

                        if is_createur(guild_id, target_id):
                            if not is_createur(guild_id, punisher_id):
                                try:
                                    await punisher.move_to(None)
                                    await punisher.send("⛔ Tu ne peux pas déconnecter un **Créateur** !")
                                except:
                                    pass

                        elif is_owner(guild_id, target_id):
                            if not is_owner(guild_id, punisher_id) and not is_createur(guild_id, punisher_id):
                                try:
                                    await punisher.move_to(None)
                                    await punisher.send("⛔ Tu ne peux pas déconnecter un **Owner** !")
                                except:
                                    pass
                        break
            except:
                pass

    # Protection move
    if before.channel and after.channel and before.channel != after.channel:
        target_id = str(member.id)
        if is_createur(guild_id, target_id) or is_owner(guild_id, target_id):
            await asyncio.sleep(1)
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_move):
                    punisher = entry.user
                    punisher_id = str(punisher.id)

                    if is_createur(guild_id, target_id):
                        if not is_createur(guild_id, punisher_id):
                            try:
                                await punisher.move_to(None)
                                await punisher.send("⛔ Tu ne peux pas move un **Créateur** !")
                            except:
                                pass

                    elif is_owner(guild_id, target_id):
                        if not is_owner(guild_id, punisher_id) and not is_createur(guild_id, punisher_id):
                            try:
                                await punisher.move_to(None)
                                await punisher.send("⛔ Tu ne peux pas move un **Owner** !")
                            except:
                                pass
                    break
            except:
                pass

# ==================== COMMANDES ====================
@bot.command(name="createur")
@commands.has_permissions(administrator=True)
async def add_createur(ctx, member: discord.Member):
    guild_id = str(ctx.guild.id)
    if guild_id not in data["createurs"]:
        data["createurs"][guild_id] = []
    if str(member.id) in data["createurs"][guild_id]:
        await ctx.send(f"❌ {member.mention} est déjà Créateur !")
        return
    data["createurs"][guild_id].append(str(member.id))
    save_data()
    await ctx.send(f"✅ {member.mention} est maintenant **Créateur** 👑")

@bot.command(name="uncreateur")
@commands.has_permissions(administrator=True)
async def remove_createur(ctx, member: discord.Member):
    guild_id = str(ctx.guild.id)
    if guild_id not in data["createurs"] or str(member.id) not in data["createurs"][guild_id]:
        await ctx.send(f"❌ {member.mention} n'est pas Créateur !")
        return
    data["createurs"][guild_id].remove(str(member.id))
    save_data()
    await ctx.send(f"✅ {member.mention} n'est plus Créateur.")

@bot.command(name="owner")
async def add_owner(ctx, member: discord.Member):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)
    if not is_createur(guild_id, user_id) and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Seul un **Créateur** peut assigner des Owners !")
        return
    if guild_id not in data["owners"]:
        data["owners"][guild_id] = []
    if str(member.id) in data["owners"][guild_id]:
        await ctx.send(f"❌ {member.mention} est déjà Owner !")
        return
    data["owners"][guild_id].append(str(member.id))
    save_data()
    await ctx.send(f"✅ {member.mention} est maintenant **Owner** ⭐")

@bot.command(name="unowner")
async def remove_owner(ctx, member: discord.Member):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)
    if not is_createur(guild_id, user_id) and not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Seul un **Créateur** peut retirer des Owners !")
        return
    if guild_id not in data["owners"] or str(member.id) not in data["owners"][guild_id]:
        await ctx.send(f"❌ {member.mention} n'est pas Owner !")
        return
    data["owners"][guild_id].remove(str(member.id))
    save_data()
    await ctx.send(f"✅ {member.mention} n'est plus Owner.")

@bot.command(name="pv")
async def pv(ctx, channel: discord.VoiceChannel = None):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    if not is_createur(guild_id, user_id) and not is_owner(guild_id, user_id):
        await ctx.send("❌ Tu n'as pas la permission de faire ça !")
        return

    if channel is None:
        if ctx.author.voice:
            channel = ctx.author.voice.channel
        else:
            await ctx.send("❌ Spécifie une voc ou rejoins-en une ! Ex: `=pv`")
            return

    if not isinstance(channel, discord.VoiceChannel):
        await ctx.send("❌ Tu peux seulement mettre en privé un salon **vocal** !")
        return

    channel_id = str(channel.id)

    if guild_id not in data["pv_channels"]:
        data["pv_channels"][guild_id] = {}

    if channel_id in data["pv_channels"][guild_id]:
        del data["pv_channels"][guild_id][channel_id]
        save_data()
        try:
            await channel.set_permissions(ctx.guild.default_role, connect=None)
        except:
            pass
        embed = discord.Embed(title="🔓 Voc déverrouillée", description=f"**{channel.name}** est maintenant **publique** !", color=discord.Color.green())
        await ctx.send(embed=embed)
    else:
        data["pv_channels"][guild_id][channel_id] = {"whitelist": []}
        save_data()
        try:
            await channel.set_permissions(ctx.guild.default_role, connect=False)
        except:
            pass
        embed = discord.Embed(title="🔒 Voc privée activée", description=f"**{channel.name}** est maintenant **privée** !\n\n`=addpv @user` — Autoriser quelqu'un\n`=decoall` — Deco tout le monde", color=discord.Color.red())
        await ctx.send(embed=embed)

@bot.command(name="addpv")
async def add_whitelist(ctx, member: discord.Member, channel: discord.VoiceChannel = None):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    if not is_createur(guild_id, user_id) and not is_owner(guild_id, user_id):
        await ctx.send("❌ Tu n'as pas la permission !")
        return

    if channel is None:
        if ctx.author.voice:
            channel = ctx.author.voice.channel
        else:
            await ctx.send("❌ Spécifie une voc ou rejoins-en une !")
            return

    channel_id = str(channel.id)

    if not is_pv(guild_id, channel_id):
        await ctx.send("❌ Cette voc n'est pas en mode privé !")
        return

    if str(member.id) not in data["pv_channels"][guild_id][channel_id]["whitelist"]:
        data["pv_channels"][guild_id][channel_id]["whitelist"].append(str(member.id))
        save_data()

    try:
        await channel.set_permissions(member, connect=True)
    except:
        pass

    await ctx.send(f"✅ {member.mention} peut maintenant rejoindre **{channel.name}** !")

@bot.command(name="rmpv")
async def remove_whitelist(ctx, member: discord.Member, channel: discord.VoiceChannel = None):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    if not is_createur(guild_id, user_id) and not is_owner(guild_id, user_id):
        await ctx.send("❌ Tu n'as pas la permission !")
        return

    if channel is None:
        if ctx.author.voice:
            channel = ctx.author.voice.channel
        else:
            await ctx.send("❌ Spécifie une voc ou rejoins-en une !")
            return

    channel_id = str(channel.id)

    if not is_pv(guild_id, channel_id):
        await ctx.send("❌ Cette voc n'est pas en mode privé !")
        return

    if str(member.id) in data["pv_channels"][guild_id][channel_id]["whitelist"]:
        data["pv_channels"][guild_id][channel_id]["whitelist"].remove(str(member.id))
        save_data()

    try:
        await channel.set_permissions(member, connect=False)
    except:
        pass

    await ctx.send(f"✅ {member.mention} ne peut plus rejoindre **{channel.name}** !")

@bot.command(name="decoall")
async def deco_all(ctx, channel: discord.VoiceChannel = None):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    if not is_createur(guild_id, user_id) and not is_owner(guild_id, user_id):
        await ctx.send("❌ Tu n'as pas la permission !")
        return

    if channel is None:
        if ctx.author.voice:
            channel = ctx.author.voice.channel
        else:
            await ctx.send("❌ Spécifie une voc ou rejoins-en une !")
            return

    count = 0
    for member in channel.members:
        if str(member.id) == user_id:
            continue
        if is_owner(guild_id, user_id) and is_createur(guild_id, str(member.id)):
            continue
        try:
            await member.move_to(None)
            count += 1
        except:
            pass

    await ctx.send(f"✅ **{count}** membre(s) déconnecté(s) de **{channel.name}** !")

@bot.command(name="listpv")
async def list_pv(ctx):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    if not is_createur(guild_id, user_id) and not is_owner(guild_id, user_id):
        await ctx.send("❌ Tu n'as pas la permission !")
        return

    if guild_id not in data["pv_channels"] or not data["pv_channels"][guild_id]:
        await ctx.send("🔓 Aucune voc privée active.")
        return

    embed = discord.Embed(title="🔒 Vocs Privées Actives", color=discord.Color.red())
    for ch_id, info in data["pv_channels"][guild_id].items():
        channel = ctx.guild.get_channel(int(ch_id))
        if channel:
            whitelist = info.get("whitelist", [])
            wl_mentions = ", ".join([f"<@{uid}>" for uid in whitelist]) if whitelist else "Personne"
            embed.add_field(name=f"🔒 {channel.name}", value=f"Whitelist: {wl_mentions}", inline=False)

    await ctx.send(embed=embed)

@bot.command(name="vhelp")
async def vhelp(ctx):
    embed = discord.Embed(title="📚 Commandes Vocal Bot", color=discord.Color.blue())
    embed.add_field(name="👑 Créateur (admin only)", value="`=createur @user`\n`=uncreateur @user`", inline=False)
    embed.add_field(name="⭐ Owner (créateur only)", value="`=owner @user`\n`=unowner @user`", inline=False)
    embed.add_field(name="🔒 Voc Privée", value="`=pv` — Toggle privé\n`=addpv @user` — Autoriser\n`=rmpv @user` — Retirer\n`=decoall` — Deco tout le monde\n`=listpv` — Liste des vocs privées", inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Tu n'as pas les permissions nécessaires !")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Membre introuvable !")
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send("❌ Salon introuvable !")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Erreur: {error}")

if __name__ == "__main__":
    bot.run(TOKEN)