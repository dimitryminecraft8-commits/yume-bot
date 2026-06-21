import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import random
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TOKEN")
DATA_FILE = "utilitaire_data.json"

EMOJIS = [
    "🎆", "🎇", "✨", "🎉", "🎊", "🎈", "🎀", "🎁", "🌟", "⭐",
    "💫", "🔥", "🌈", "🌸", "🌺", "🌼", "🌻", "🍀", "🦋", "🐬",
    "🌙", "☀️", "⚡", "❄️", "💎", "🔮", "🎵", "🎶", "🎮", "🕹️",
    "🚀", "🛸", "🌌", "🪐", "💜", "💙", "💚", "💛", "🧡", "❤️",
    "🖤", "🤍", "🤎", "💗", "💖", "💝", "🎯", "🎲", "🃏", "🎰",
]

# ==================== INITIALISATION ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="=", intents=intents)

data = {
    "createurs": {},
    "owners": {},
    "pv_channels": {},
    "logs": {},
}

join_tracker = defaultdict(lambda: defaultdict(list))
bot_actions = set()

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
            for key in data:
                if key in loaded:
                    data[key] = loaded[key]

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

# ==================== LOGS HELPERS ====================
def get_log_channel(guild, log_type):
    guild_id = str(guild.id)
    if guild_id not in data["logs"]:
        return None
    channel_id = data["logs"][guild_id].get(log_type)
    if not channel_id:
        return None
    return guild.get_channel(int(channel_id))

async def send_log(guild, log_type, embed):
    channel = get_log_channel(guild, log_type)
    if channel:
        try:
            await channel.send(embed=embed)
        except:
            pass

# ==================== ON READY ====================
@bot.event
async def on_ready():
    print(f"✅ Utilitaire Bot connecté: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"📊 {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur sync: {e}")

# ==================== VOICE STATE (vocal protection + logs) ====================
@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild
    guild_id = str(guild.id)
    user_id = str(member.id)

    # ---------- LOGS VOCAL ----------
    if not before.channel and after.channel:
        embed = discord.Embed(description=f"🎙️ {member.mention} a **rejoint** {after.channel.mention}", color=discord.Color.green(), timestamp=datetime.now())
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        await send_log(guild, "vocal", embed)
    elif before.channel and not after.channel:
        embed = discord.Embed(description=f"🎙️ {member.mention} a **quitté** {before.channel.mention}", color=discord.Color.red(), timestamp=datetime.now())
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        await send_log(guild, "vocal", embed)
    elif before.channel and after.channel and before.channel.id != after.channel.id:
        embed = discord.Embed(description=f"🎙️ {member.mention} {before.channel.mention} ➜ {after.channel.mention}", color=discord.Color.blue(), timestamp=datetime.now())
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        await send_log(guild, "vocal", embed)

    # ---------- PROTECTION VOCAL ----------
    action_key = f"{guild_id}:{user_id}"
    if action_key in bot_actions:
        return

    # Rejoindre une voc =pv
    if after.channel and is_pv(guild_id, str(after.channel.id)):
        channel_id = str(after.channel.id)
        pv_info = data["pv_channels"][guild_id][channel_id]
        whitelist = pv_info.get("whitelist", [])
        if not is_createur(guild_id, user_id) and not is_owner(guild_id, user_id) and str(user_id) not in whitelist:
            now = datetime.now()
            join_tracker[guild_id][user_id] = [t for t in join_tracker[guild_id][user_id] if (now - t).seconds < 30]
            join_tracker[guild_id][user_id].append(now)
            bot_actions.add(action_key)
            try:
                await member.move_to(None)
            except:
                pass
            await asyncio.sleep(0.5)
            bot_actions.discard(action_key)
            if len(join_tracker[guild_id][user_id]) >= 3:
                join_tracker[guild_id][user_id] = []
                try:
                    await member.timeout(timedelta(seconds=60), reason="Spam voc privée")
                    try:
                        await member.send("⛔ Tu as été expulsé 60 secondes pour avoir tenté de rejoindre une voc privée trop souvent.")
                    except:
                        pass
                except:
                    pass
        return

    # Protection DECO
    if before.channel and not after.channel:
        target_id = str(member.id)
        if is_createur(guild_id, target_id) or is_owner(guild_id, target_id):
            await asyncio.sleep(1)
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_disconnect):
                    if entry.target.id == member.id:
                        punisher = entry.user
                        punisher_id = str(punisher.id)
                        if punisher_id == str(bot.user.id):
                            break
                        should_punish = False
                        if is_createur(guild_id, target_id):
                            if not is_createur(guild_id, punisher_id):
                                should_punish = True
                        elif is_owner(guild_id, target_id):
                            if not is_owner(guild_id, punisher_id) and not is_createur(guild_id, punisher_id):
                                should_punish = True
                        if should_punish:
                            try:
                                if punisher.voice:
                                    await punisher.move_to(None)
                                await punisher.timeout(timedelta(seconds=10), reason="A tenté de déco un protégé")
                                try:
                                    await punisher.send("⛔ Tu ne peux pas déconnecter cette personne ! Timeout 10 secondes.")
                                except:
                                    pass
                            except Exception as e:
                                print(f"Erreur punition deco: {e}")
                        break
            except Exception as e:
                print(f"Erreur audit deco: {e}")
        return

    # Protection MOVE
    if before.channel and after.channel and before.channel.id != after.channel.id:
        target_id = str(member.id)
        original_channel = before.channel
        if is_createur(guild_id, target_id) or is_owner(guild_id, target_id):
            await asyncio.sleep(1)
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_move):
                    punisher = entry.user
                    punisher_id = str(punisher.id)
                    if punisher_id == str(bot.user.id):
                        break
                    should_punish = False
                    if is_createur(guild_id, target_id):
                        if not is_createur(guild_id, punisher_id):
                            should_punish = True
                    elif is_owner(guild_id, target_id):
                        if not is_owner(guild_id, punisher_id) and not is_createur(guild_id, punisher_id):
                            should_punish = True
                    if should_punish:
                        bot_actions.add(action_key)
                        try:
                            await member.move_to(original_channel)
                        except:
                            pass
                        await asyncio.sleep(0.5)
                        bot_actions.discard(action_key)
                        try:
                            if punisher.voice:
                                await punisher.move_to(None)
                            await punisher.timeout(timedelta(seconds=10), reason="A tenté de move un protégé")
                            try:
                                await punisher.send("⛔ Tu ne peux pas move cette personne ! Timeout 10 secondes.")
                            except:
                                pass
                        except Exception as e:
                            print(f"Erreur punition move: {e}")
                    break
            except Exception as e:
                print(f"Erreur audit move: {e}")
        return

# ==================== LOGS EVENTS ====================
@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    embed = discord.Embed(title="🗑️ Message supprimé", description=f"**Auteur:** {message.author.mention}\n**Salon:** {message.channel.mention}\n**Contenu:**\n{message.content[:1000] if message.content else '*(aucun texte)*'}", color=discord.Color.red(), timestamp=datetime.now())
    embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    await send_log(message.guild, "messages", embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    embed = discord.Embed(title="✏️ Message modifié", description=f"**Auteur:** {before.author.mention}\n**Salon:** {before.channel.mention}", color=discord.Color.orange(), timestamp=datetime.now())
    embed.add_field(name="Avant", value=before.content[:500] if before.content else "*(vide)*", inline=False)
    embed.add_field(name="Après", value=after.content[:500] if after.content else "*(vide)*", inline=False)
    embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
    await send_log(before.guild, "messages", embed)

@bot.event
async def on_member_join(member):
    embed = discord.Embed(title="📥 Membre rejoint", description=f"{member.mention}\n**Compte créé:** {member.created_at.strftime('%d/%m/%Y')}", color=discord.Color.green(), timestamp=datetime.now())
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    embed.set_footer(text=f"Membre #{member.guild.member_count}")
    await send_log(member.guild, "members", embed)

@bot.event
async def on_member_remove(member):
    embed = discord.Embed(title="📤 Membre parti", description=f"{member.mention} ({member.name})", color=discord.Color.red(), timestamp=datetime.now())
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    await send_log(member.guild, "members", embed)

@bot.event
async def on_member_update(before, after):
    added = set(after.roles) - set(before.roles)
    removed = set(before.roles) - set(after.roles)
    for role in added:
        embed = discord.Embed(description=f"🎭 {after.mention} a reçu {role.mention}", color=discord.Color.green(), timestamp=datetime.now())
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        await send_log(after.guild, "roles", embed)
    for role in removed:
        embed = discord.Embed(description=f"🎭 {after.mention} a perdu {role.mention}", color=discord.Color.red(), timestamp=datetime.now())
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        await send_log(after.guild, "roles", embed)

@bot.event
async def on_guild_channel_create(channel):
    embed = discord.Embed(title="➕ Salon créé", description=f"**Nom:** {channel.name}\n**Type:** {channel.type}", color=discord.Color.green(), timestamp=datetime.now())
    await send_log(channel.guild, "server", embed)

@bot.event
async def on_guild_channel_delete(channel):
    embed = discord.Embed(title="➖ Salon supprimé", description=f"**Nom:** {channel.name}\n**Type:** {channel.type}", color=discord.Color.red(), timestamp=datetime.now())
    await send_log(channel.guild, "server", embed)

@bot.event
async def on_member_ban(guild, user):
    embed = discord.Embed(title="🔨 Membre banni", description=f"{user.mention} ({user.name})", color=discord.Color.dark_red(), timestamp=datetime.now())
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    await send_log(guild, "moderation", embed)

@bot.event
async def on_member_unban(guild, user):
    embed = discord.Embed(title="🔓 Membre débanni", description=f"{user.mention} ({user.name})", color=discord.Color.green(), timestamp=datetime.now())
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    await send_log(guild, "moderation", embed)

# ==================== COMMANDES VOCAL (=) ====================
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
            await ctx.send("❌ Spécifie une voc ou rejoins-en une !")
            return
    if not isinstance(channel, discord.VoiceChannel):
        await ctx.send("❌ Tu peux seulement mettre en privé un salon **vocal** !")
        return
    channel_id = str(channel.id)
    if guild_id not in data["pv_channels"]:
        data["pv_channels"][guild_id] = {}
    if channel_id in data["pv_channels"][guild_id]:
        pv_info = data["pv_channels"][guild_id][channel_id]
        locked_by = pv_info.get("locked_by", "owner")
        if locked_by == "createur" and not is_createur(guild_id, user_id):
            await ctx.send("❌ Cette voc a été verrouillée par un **Créateur**, seul un Créateur peut la déverrouiller !")
            return
        del data["pv_channels"][guild_id][channel_id]
        save_data()
        try:
            await channel.set_permissions(ctx.guild.default_role, overwrite=None)
        except:
            pass
        embed = discord.Embed(title="🔓 Voc déverrouillée", description=f"**{channel.name}** est maintenant **publique** !", color=discord.Color.green())
        await ctx.send(embed=embed)
    else:
        locked_by = "createur" if is_createur(guild_id, user_id) else "owner"
        data["pv_channels"][guild_id][channel_id] = {"whitelist": [], "locked_by": locked_by}
        save_data()
        try:
            overwrite = discord.PermissionOverwrite()
            overwrite.connect = False
            overwrite.send_messages = False
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            author_overwrite = discord.PermissionOverwrite()
            author_overwrite.connect = True
            author_overwrite.send_messages = True
            author_overwrite.speak = True
            await channel.set_permissions(ctx.author, overwrite=author_overwrite)
        except Exception as e:
            print(f"Erreur permissions pv: {e}")
        for cid in data["createurs"].get(guild_id, []):
            cmember = ctx.guild.get_member(int(cid))
            if cmember:
                try:
                    c_overwrite = discord.PermissionOverwrite()
                    c_overwrite.connect = True
                    c_overwrite.send_messages = True
                    c_overwrite.speak = True
                    await channel.set_permissions(cmember, overwrite=c_overwrite)
                except:
                    pass
        msg = "👑 Seul un **Créateur** peut la déverrouiller." if locked_by == "createur" else "⭐ Un **Owner** ou **Créateur** peut la déverrouiller."
        embed = discord.Embed(title="🔒 Voc privée activée", description=f"**{channel.name}** est maintenant **privée** !\n\n{msg}\n\n`=addpv @user` — Autoriser\n`=decoall` — Deco tout le monde", color=discord.Color.red())
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
        ow = discord.PermissionOverwrite()
        ow.connect = True
        await channel.set_permissions(member, overwrite=ow)
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
        await channel.set_permissions(member, overwrite=None)
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
        mkey = f"{guild_id}:{member.id}"
        bot_actions.add(mkey)
        try:
            await member.move_to(None)
            count += 1
        except:
            pass
        await asyncio.sleep(0.3)
        bot_actions.discard(mkey)
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
            locked_by = info.get("locked_by", "owner")
            wl_mentions = ", ".join([f"<@{uid}>" for uid in whitelist]) if whitelist else "Personne"
            embed.add_field(name=f"🔒 {channel.name} ({locked_by})", value=f"Whitelist: {wl_mentions}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="vhelp")
async def vhelp(ctx):
    embed = discord.Embed(title="📚 Commandes Vocal", color=discord.Color.blue())
    embed.add_field(name="👑 Créateur (admin only)", value="`=createur @user`\n`=uncreateur @user`", inline=False)
    embed.add_field(name="⭐ Owner (créateur only)", value="`=owner @user`\n`=unowner @user`", inline=False)
    embed.add_field(name="🔒 Voc Privée", value="`=pv` `=addpv @user` `=rmpv @user`\n`=decoall` `=listpv`", inline=False)
    await ctx.send(embed=embed)

# ==================== SLASH SETUP (création salons) ====================
@bot.tree.command(name="createvocals", description="🔊 Créer plusieurs salons vocaux numérotés")
@app_commands.describe(name="Nom de base", start="Numéro de départ", end="Numéro de fin", category="Catégorie", user_limit="Membres max (0=illimité)", emoji="Emoji random ?")
@app_commands.checks.has_permissions(administrator=True)
async def createvocals(interaction: discord.Interaction, name: str, start: int, end: int, category: Optional[discord.CategoryChannel] = None, user_limit: int = 0, emoji: bool = True):
    if start > end:
        await interaction.response.send_message("❌ Numéro de départ doit être inférieur à la fin !", ephemeral=True)
        return
    total = end - start + 1
    if total > 300:
        await interaction.response.send_message("❌ Maximum 300 salons à la fois !", ephemeral=True)
        return
    await interaction.response.send_message(f"🔨 Création de **{total}** vocaux...", ephemeral=True)
    created = 0
    for i in range(start, end + 1):
        channel_name = f"{random.choice(EMOJIS)} {name} {i}" if emoji else f"{name} {i}"
        try:
            await interaction.guild.create_voice_channel(name=channel_name, category=category, user_limit=user_limit if user_limit > 0 else None)
            created += 1
            if created % 5 == 0:
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Erreur: {e}")
    await interaction.followup.send(f"✅ **{created}** vocaux créés !", ephemeral=True)

@bot.tree.command(name="createtext", description="💬 Créer plusieurs salons textuels numérotés")
@app_commands.describe(name="Nom de base", start="Numéro de départ", end="Numéro de fin", category="Catégorie", emoji="Emoji random ?")
@app_commands.checks.has_permissions(administrator=True)
async def createtext(interaction: discord.Interaction, name: str, start: int, end: int, category: Optional[discord.CategoryChannel] = None, emoji: bool = True):
    if start > end:
        await interaction.response.send_message("❌ Numéro de départ doit être inférieur à la fin !", ephemeral=True)
        return
    total = end - start + 1
    if total > 300:
        await interaction.response.send_message("❌ Maximum 300 salons !", ephemeral=True)
        return
    await interaction.response.send_message(f"🔨 Création de **{total}** salons texte...", ephemeral=True)
    created = 0
    for i in range(start, end + 1):
        channel_name = f"{random.choice(EMOJIS)}-{name}-{i}" if emoji else f"{name}-{i}"
        try:
            await interaction.guild.create_text_channel(name=channel_name, category=category)
            created += 1
            if created % 5 == 0:
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Erreur: {e}")
    await interaction.followup.send(f"✅ **{created}** salons texte créés !", ephemeral=True)

@bot.tree.command(name="createcategory", description="📁 Créer une catégorie")
@app_commands.describe(name="Nom de la catégorie", staff_only="Réservée à un rôle ?")
@app_commands.checks.has_permissions(administrator=True)
async def createcategory(interaction: discord.Interaction, name: str, staff_only: Optional[discord.Role] = None):
    await interaction.response.defer(ephemeral=True)
    overwrites = {}
    if staff_only:
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False), staff_only: discord.PermissionOverwrite(view_channel=True)}
    try:
        category = await interaction.guild.create_category(name=name, overwrites=overwrites)
        msg = f"✅ Catégorie **{category.name}** créée !"
        if staff_only:
            msg += f"\n🔒 Visible par {staff_only.mention}"
        await interaction.followup.send(msg, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

@bot.tree.command(name="setupserver", description="🏗️ Créer une catégorie avec des vocaux d'un coup")
@app_commands.describe(category_name="Nom catégorie", vocal_name="Nom des vocaux", count="Nombre de vocaux", user_limit="Membres max", staff_only="Réservée à un rôle ?")
@app_commands.checks.has_permissions(administrator=True)
async def setupserver(interaction: discord.Interaction, category_name: str, vocal_name: str, count: int, user_limit: int = 0, staff_only: Optional[discord.Role] = None):
    if count > 300:
        await interaction.response.send_message("❌ Maximum 300 vocaux !", ephemeral=True)
        return
    await interaction.response.send_message(f"🏗️ Création catégorie **{category_name}** avec **{count}** vocaux...", ephemeral=True)
    overwrites = {}
    if staff_only:
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False), staff_only: discord.PermissionOverwrite(view_channel=True)}
    try:
        category = await interaction.guild.create_category(name=category_name, overwrites=overwrites)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)
        return
    created = 0
    for i in range(1, count + 1):
        channel_name = f"{random.choice(EMOJIS)} {vocal_name} {i}"
        try:
            await interaction.guild.create_voice_channel(name=channel_name, category=category, user_limit=user_limit if user_limit > 0 else None)
            created += 1
            if created % 5 == 0:
                await asyncio.sleep(1)
        except:
            pass
    await interaction.followup.send(f"✅ Catégorie **{category_name}** créée avec **{created}** vocaux !", ephemeral=True)

@bot.tree.command(name="deletevocals", description="🗑️ Supprimer tous les vocaux d'une catégorie")
@app_commands.describe(category="Catégorie")
@app_commands.checks.has_permissions(administrator=True)
async def deletevocals(interaction: discord.Interaction, category: discord.CategoryChannel):
    await interaction.response.send_message(f"🗑️ Suppression des vocaux de **{category.name}**...", ephemeral=True)
    deleted = 0
    for channel in category.voice_channels:
        try:
            await channel.delete()
            deleted += 1
            if deleted % 5 == 0:
                await asyncio.sleep(1)
        except:
            pass
    await interaction.followup.send(f"✅ **{deleted}** vocaux supprimés !", ephemeral=True)

@bot.tree.command(name="deletetext", description="🗑️ Supprimer tous les salons texte d'une catégorie")
@app_commands.describe(category="Catégorie")
@app_commands.checks.has_permissions(administrator=True)
async def deletetext(interaction: discord.Interaction, category: discord.CategoryChannel):
    await interaction.response.send_message(f"🗑️ Suppression des salons texte de **{category.name}**...", ephemeral=True)
    deleted = 0
    for channel in category.text_channels:
        try:
            await channel.delete()
            deleted += 1
            if deleted % 5 == 0:
                await asyncio.sleep(1)
        except:
            pass
    await interaction.followup.send(f"✅ **{deleted}** salons texte supprimés !", ephemeral=True)

# ==================== SLASH LOGS ====================
@bot.tree.command(name="setlog", description="📋 Définir un salon de logs pour un type")
@app_commands.describe(type="Type de log", channel="Salon")
@app_commands.choices(type=[
    app_commands.Choice(name="🎙️ Vocal", value="vocal"),
    app_commands.Choice(name="💬 Messages", value="messages"),
    app_commands.Choice(name="👤 Membres", value="members"),
    app_commands.Choice(name="🎭 Rôles", value="roles"),
    app_commands.Choice(name="⚙️ Serveur", value="server"),
    app_commands.Choice(name="🔨 Modération", value="moderation"),
])
@app_commands.checks.has_permissions(administrator=True)
async def setlog(interaction: discord.Interaction, type: str, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["logs"]:
        data["logs"][guild_id] = {}
    data["logs"][guild_id][type] = str(channel.id)
    save_data()
    await interaction.response.send_message(f"✅ Logs **{type}** dans {channel.mention}")

@bot.tree.command(name="setalllogs", description="🏗️ Tous les logs dans un seul salon")
@app_commands.describe(channel="Salon")
@app_commands.checks.has_permissions(administrator=True)
async def setalllogs(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    data["logs"][guild_id] = {k: str(channel.id) for k in ["vocal", "messages", "members", "roles", "server", "moderation"]}
    save_data()
    await interaction.response.send_message(f"✅ Tous les logs dans {channel.mention}")

@bot.tree.command(name="removelog", description="❌ Retirer un type de log")
@app_commands.describe(type="Type")
@app_commands.choices(type=[
    app_commands.Choice(name="🎙️ Vocal", value="vocal"),
    app_commands.Choice(name="💬 Messages", value="messages"),
    app_commands.Choice(name="👤 Membres", value="members"),
    app_commands.Choice(name="🎭 Rôles", value="roles"),
    app_commands.Choice(name="⚙️ Serveur", value="server"),
    app_commands.Choice(name="🔨 Modération", value="moderation"),
])
@app_commands.checks.has_permissions(administrator=True)
async def removelog(interaction: discord.Interaction, type: str):
    guild_id = str(interaction.guild.id)
    if guild_id in data["logs"] and type in data["logs"][guild_id]:
        del data["logs"][guild_id][type]
        save_data()
        await interaction.response.send_message(f"✅ Logs **{type}** désactivés.")
    else:
        await interaction.response.send_message(f"❌ Aucun salon pour **{type}**.", ephemeral=True)

@bot.tree.command(name="logconfig", description="📋 Voir la config des logs")
@app_commands.checks.has_permissions(administrator=True)
async def logconfig(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["logs"] or not data["logs"][guild_id]:
        await interaction.response.send_message("❌ Aucun log configuré.", ephemeral=True)
        return
    embed = discord.Embed(title="📋 Configuration des Logs", color=discord.Color.blue())
    types = {"vocal": "🎙️ Vocal", "messages": "💬 Messages", "members": "👤 Membres", "roles": "🎭 Rôles", "server": "⚙️ Serveur", "moderation": "🔨 Modération"}
    for key, label in types.items():
        ch_id = data["logs"][guild_id].get(key)
        if ch_id:
            channel = interaction.guild.get_channel(int(ch_id))
            value = channel.mention if channel else "❌ Salon supprimé"
        else:
            value = "❌ Non configuré"
        embed.add_field(name=label, value=value, inline=True)
    await interaction.response.send_message(embed=embed)

# ==================== ERREURS ====================
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

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        try:
            await interaction.response.send_message("❌ Tu n'as pas les permissions nécessaires !", ephemeral=True)
        except:
            pass
    else:
        print(f"Erreur slash: {error}")

# ==================== LANCEMENT ====================
if __name__ == "__main__":
    bot.run(TOKEN)