import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TOKEN")  # <-- Mets ton token ici
DATA_FILE = "bot_data.json"

# Couleurs pour les embeds
COLORS = {
    "success": discord.Color.green(),
    "error": discord.Color.red(),
    "warn": discord.Color.orange(),
    "info": discord.Color.blue(),
    "protect": discord.Color.gold()
}

# ==================== INITIALISATION ====================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Données du bot
data = {
    "protected_users": {},
    "mutes": {},
    "warns": {},
    "ranks": {}
}

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, default=str)

load_data()

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"📊 {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur sync: {e}")
    check_mutes.start()
    check_unbans.start()

@bot.event
async def on_member_remove(member):
    guild_id = str(member.guild.id)
    user_id = str(member.id)
    if guild_id not in data["protected_users"] or user_id not in data["protected_users"][guild_id]:
        return

    await asyncio.sleep(2)
    try:
        # Vérifier si c'est un BAN
        async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
            if entry.target.id == member.id:
                # Débannir la personne protégée
                await member.guild.unban(member, reason="🛡️ Utilisateur protégé - Auto unban")

                # Punir celui qui a banni (ban si pas admin, sinon kick)
                punisher = entry.user
                if not punisher.guild_permissions.administrator:
                    try:
                        await punisher.send(f"🚨 Tu as tenté de bannir **{member.name}** qui est PROTÉGÉ ! Tu es banni en retour.")
                    except:
                        pass
                    await member.guild.ban(punisher, reason=f"🛡️ A tenté de bannir un utilisateur protégé ({member.name})")
                    await log_action(member.guild, "🚨 BAN BLOQUÉ + PUNITION",
                        f"{punisher.mention} a tenté de bannir {member.mention} (protégé)\n**→ {punisher.mention} a été banni en retour !**",
                        COLORS["protect"])
                else:
                    # C'est un admin, on kick à la place
                    try:
                        await punisher.send(f"🚨 Tu as tenté de bannir **{member.name}** qui est PROTÉGÉ ! Action annulée.")
                    except:
                        pass
                    await log_action(member.guild, "🚨 BAN BLOQUÉ",
                        f"{punisher.mention} (admin) a tenté de bannir {member.mention} (protégé)\n**→ Unban automatique effectué.**",
                        COLORS["protect"])
                return

        # Vérifier si c'est un KICK
        async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
            if entry.target.id == member.id:
                punisher = entry.user
                if not punisher.guild_permissions.administrator:
                    try:
                        await punisher.send(f"🚨 Tu as tenté de kicker **{member.name}** qui est PROTÉGÉ ! Tu es banni en retour.")
                    except:
                        pass
                    await member.guild.ban(punisher, reason=f"🛡️ A tenté de kicker un utilisateur protégé ({member.name})")
                    await log_action(member.guild, "🚨 KICK BLOQUÉ + PUNITION",
                        f"{punisher.mention} a tenté de kicker {member.mention} (protégé)\n**→ {punisher.mention} a été banni en retour !**",
                        COLORS["protect"])
                else:
                    try:
                        await punisher.send(f"🚨 Tu as tenté de kicker **{member.name}** qui est PROTÉGÉ ! Action notée.")
                    except:
                        pass
                    await log_action(member.guild, "🚨 KICK BLOQUÉ",
                        f"{punisher.mention} (admin) a tenté de kicker {member.mention} (protégé)",
                        COLORS["protect"])
                return

    except Exception as e:
        print(f"Erreur protection: {e}")

@bot.event
async def on_member_update(before, after):
    guild_id = str(after.guild.id)
    user_id = str(after.id)
    if guild_id not in data["protected_users"] or user_id not in data["protected_users"][guild_id]:
        return
    removed_roles = list(set(before.roles) - set(after.roles))
    if removed_roles:
        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
            if entry.target.id == after.id:
                for role in removed_roles:
                    try:
                        await after.add_roles(role, reason="🛡️ Utilisateur protégé - Restauration auto")
                    except:
                        pass
                try:
                    await entry.user.send(f"⚠️ Tu as tenté de retirer des rôles à {after.name} qui est **PROTÉGÉ** !")
                except:
                    pass
                await log_action(after.guild, "🚨 DERANK BLOQUÉ",
                    f"{entry.user.mention} a tenté de retirer des rôles à {after.mention}",
                    COLORS["protect"])
                break

# ==================== TÂCHES EN ARRIÈRE-PLAN ====================
@tasks.loop(seconds=30)
async def check_mutes():
    now = datetime.now()
    for guild_id in list(data["mutes"].keys()):
        for user_id in list(data["mutes"][guild_id].keys()):
            mute_info = data["mutes"][guild_id][user_id]
            if datetime.fromisoformat(mute_info["end_time"]) <= now:
                guild = bot.get_guild(int(guild_id))
                if guild:
                    member = guild.get_member(int(user_id))
                    if member:
                        mute_role = discord.utils.get(guild.roles, name="Muted")
                        if mute_role and mute_role in member.roles:
                            await member.remove_roles(mute_role)
                        for role_id in mute_info["roles"]:
                            role = guild.get_role(int(role_id))
                            if role:
                                await member.add_roles(role)
                        try:
                            await member.send(f"🔊 Tu as été **unmute** automatiquement sur {guild.name}")
                        except:
                            pass
                del data["mutes"][guild_id][user_id]
                save_data()

@tasks.loop(minutes=1)
async def check_unbans():
    pass

# ==================== FONCTIONS UTILITAIRES ====================
async def log_action(guild, title, description, color):
    log_channel = (
        discord.utils.get(guild.text_channels, name="logs") or
        discord.utils.get(guild.text_channels, name="mod-logs") or
        discord.utils.get(guild.text_channels, name="bot-logs")
    )
    if log_channel:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now())
        await log_channel.send(embed=embed)

def parse_time(time_str):
    if not time_str:
        return None
    time_str = time_str.lower()
    total_seconds = 0
    import re
    patterns = [
        (r'(\d+)d', 86400),
        (r'(\d+)h', 3600),
        (r'(\d+)m', 60),
        (r'(\d+)s', 1),
    ]
    for pattern, seconds in patterns:
        matches = re.findall(pattern, time_str)
        for match in matches:
            total_seconds += int(match) * seconds
    return timedelta(seconds=total_seconds) if total_seconds > 0 else None

# ==================== PROTECTION ====================
@bot.tree.command(name="protect", description="🛡️ Protéger un utilisateur contre les sanctions")
@app_commands.describe(user="Utilisateur à protéger")
@app_commands.checks.has_permissions(administrator=True)
async def protect(interaction: discord.Interaction, user: discord.Member):
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id not in data["protected_users"]:
        data["protected_users"][guild_id] = []
    if user_id in data["protected_users"][guild_id]:
        await interaction.response.send_message(f"❌ {user.mention} est déjà protégé !", ephemeral=True)
        return
    data["protected_users"][guild_id].append(user_id)
    save_data()
    embed = discord.Embed(
        title="🛡️ Protection Activée",
        description=f"{user.mention} est maintenant **immunisé** contre :\n• Ban\n• Kick\n• Retrait de rôles",
        color=COLORS["protect"]
    )
    embed.set_footer(text=f"Protégé par {interaction.user.name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unprotect", description="⚠️ Retirer la protection d'un utilisateur")
@app_commands.describe(user="Utilisateur à déprotéger")
@app_commands.checks.has_permissions(administrator=True)
async def unprotect(interaction: discord.Interaction, user: discord.Member):
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id not in data["protected_users"] or user_id not in data["protected_users"][guild_id]:
        await interaction.response.send_message(f"❌ {user.mention} n'est pas protégé !", ephemeral=True)
        return
    data["protected_users"][guild_id].remove(user_id)
    save_data()
    embed = discord.Embed(title="⚠️ Protection Retirée", description=f"{user.mention} n'est plus protégé.", color=COLORS["warn"])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="protected", description="📋 Voir la liste des utilisateurs protégés")
async def protected_list(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["protected_users"] or len(data["protected_users"][guild_id]) == 0:
        await interaction.response.send_message("🔒 Aucun utilisateur protégé.", ephemeral=True)
        return
    mentions = []
    for uid in data["protected_users"][guild_id]:
        member = interaction.guild.get_member(int(uid))
        mentions.append(f"🛡️ {member.mention}" if member else f"🛡️ <@{uid}> (hors ligne)")
    embed = discord.Embed(title="Liste des Utilisateurs Protégés", description="\n".join(mentions), color=COLORS["protect"])
    embed.set_footer(text=f"Total: {len(data['protected_users'][guild_id])}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== MODÉRATION ====================
@bot.tree.command(name="ban", description="🔨 Bannir un utilisateur")
@app_commands.describe(user="Utilisateur à bannir", reason="Raison du ban", time="Durée (ex: 1d, 12h, 30m)")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = "Aucune raison", time: Optional[str] = None):
    guild_id = str(interaction.guild.id)
    if guild_id in data["protected_users"] and str(user.id) in data["protected_users"][guild_id]:
        await interaction.response.send_message(f"❌ Impossible de bannir {user.mention} - il est PROTÉGÉ !", ephemeral=True)
        return
    if user.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Tu ne peux pas bannir quelqu'un au-dessus de toi !", ephemeral=True)
        return
    time_str = f"pendant {time}" if time else "définitivement"
    try:
        await user.send(f"🔨 Tu as été banni de **{interaction.guild.name}**\nRaison: {reason}\nDurée: {time_str}")
    except:
        pass
    await user.ban(reason=f"{reason} | Par {interaction.user.name}")
    embed = discord.Embed(title="🔨 Utilisateur Banni", description=f"{user.mention} banni {time_str}\n**Raison:** {reason}", color=COLORS["error"])
    await interaction.response.send_message(embed=embed)
    await log_action(interaction.guild, "Ban", f"{user.name} banni par {interaction.user.name}", COLORS["error"])

@bot.tree.command(name="kick", description="👢 Expulser un utilisateur")
@app_commands.describe(user="Utilisateur à expulser", reason="Raison")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "Aucune raison"):
    guild_id = str(interaction.guild.id)
    if guild_id in data["protected_users"] and str(user.id) in data["protected_users"][guild_id]:
        await interaction.response.send_message(f"❌ Impossible d'expulser {user.mention} - il est PROTÉGÉ !", ephemeral=True)
        return
    if user.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Tu ne peux pas expulser quelqu'un au-dessus de toi !", ephemeral=True)
        return
    try:
        await user.send(f"👢 Tu as été expulsé de **{interaction.guild.name}**\nRaison: {reason}")
    except:
        pass
    await user.kick(reason=f"{reason} | Par {interaction.user.name}")
    embed = discord.Embed(title="👢 Utilisateur Expulsé", description=f"{user.mention} expulsé\n**Raison:** {reason}", color=COLORS["warn"])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="mute", description="🔇 Rendre muet un utilisateur")
@app_commands.describe(user="Utilisateur à mute", time="Durée (ex: 10m, 1h, 1d)", reason="Raison")
@app_commands.checks.has_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, user: discord.Member, time: str, reason: str = "Aucune raison"):
    guild_id = str(interaction.guild.id)
    if guild_id in data["protected_users"] and str(user.id) in data["protected_users"][guild_id]:
        await interaction.response.send_message(f"❌ Impossible de mute {user.mention} - il est PROTÉGÉ !", ephemeral=True)
        return
    duration = parse_time(time)
    if not duration:
        await interaction.response.send_message("❌ Format invalide ! Ex: 10m, 1h, 1d", ephemeral=True)
        return
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await interaction.guild.create_role(name="Muted")
        for channel in interaction.guild.channels:
            await channel.set_permissions(mute_role, speak=False, send_messages=False)
    old_roles = [r.id for r in user.roles if r.name != "@everyone"]
    await user.edit(roles=[mute_role])
    if guild_id not in data["mutes"]:
        data["mutes"][guild_id] = {}
    end_time = datetime.now() + duration
    data["mutes"][guild_id][str(user.id)] = {"end_time": end_time.isoformat(), "roles": old_roles, "reason": reason, "mod": interaction.user.id}
    save_data()
    embed = discord.Embed(title="🔇 Utilisateur Mute", description=f"{user.mention} mute pendant **{time}**\n**Raison:** {reason}", color=COLORS["warn"])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unmute", description="🔊 Démuter un utilisateur")
@app_commands.describe(user="Utilisateur à démuter")
@app_commands.checks.has_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, user: discord.Member):
    guild_id = str(interaction.guild.id)
    mute_role = discord.utils.get(interaction.guild.roles, name="Muted")
    if mute_role and mute_role in user.roles:
        await user.remove_roles(mute_role)
    if guild_id in data["mutes"] and str(user.id) in data["mutes"][guild_id]:
        for role_id in data["mutes"][guild_id][str(user.id)]["roles"]:
            role = interaction.guild.get_role(int(role_id))
            if role:
                await user.add_roles(role)
        del data["mutes"][guild_id][str(user.id)]
        save_data()
    await interaction.response.send_message(f"🔊 {user.mention} a été démuté.")

@bot.tree.command(name="warn", description="⚠️ Avertir un utilisateur")
@app_commands.describe(user="Utilisateur à avertir", reason="Raison")
@app_commands.checks.has_permissions(kick_members=True)
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str):
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id not in data["warns"]:
        data["warns"][guild_id] = {}
    if user_id not in data["warns"][guild_id]:
        data["warns"][guild_id][user_id] = []
    data["warns"][guild_id][user_id].append({"reason": reason, "mod": interaction.user.id, "date": datetime.now().isoformat()})
    save_data()
    warn_count = len(data["warns"][guild_id][user_id])
    embed = discord.Embed(title="⚠️ Avertissement", description=f"{user.mention} averti\n**Raison:** {reason}\n**Total:** {warn_count} warn(s)", color=COLORS["warn"])
    await interaction.response.send_message(embed=embed)
    try:
        await user.send(f"⚠️ Tu as été averti sur **{interaction.guild.name}**\nRaison: {reason}\nTotal: {warn_count} warn(s)")
    except:
        pass

@bot.tree.command(name="warns", description="📋 Voir les avertissements d'un utilisateur")
@app_commands.describe(user="Utilisateur (laisser vide pour soi)")
async def warns(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    target = user or interaction.user
    guild_id = str(interaction.guild.id)
    user_id = str(target.id)
    if guild_id not in data["warns"] or user_id not in data["warns"][guild_id] or len(data["warns"][guild_id][user_id]) == 0:
        await interaction.response.send_message(f"✅ {target.mention} n'a aucun avertissement.", ephemeral=True)
        return
    warns_list = data["warns"][guild_id][user_id]
    description = ""
    for i, w in enumerate(warns_list, 1):
        mod = interaction.guild.get_member(w["mod"])
        description += f"**#{i}** - {w['reason'][:50]}\nPar: {mod.name if mod else 'Inconnu'}\n\n"
    embed = discord.Embed(title=f"⚠️ Avertissements de {target.name}", description=description, color=COLORS["warn"])
    embed.set_footer(text=f"Total: {len(warns_list)}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="clearwarns", description="🗑️ Effacer les avertissements")
@app_commands.describe(user="Utilisateur")
@app_commands.checks.has_permissions(administrator=True)
async def clearwarns(interaction: discord.Interaction, user: discord.Member):
    guild_id = str(interaction.guild.id)
    user_id = str(user.id)
    if guild_id in data["warns"] and user_id in data["warns"][guild_id]:
        del data["warns"][guild_id][user_id]
        save_data()
    await interaction.response.send_message(f"🗑️ Les avertissements de {user.mention} ont été effacés.")

# ==================== RANGS ====================
@bot.tree.command(name="rank", description="⭐ Voir son profil")
@app_commands.describe(user="Utilisateur (laisser vide pour soi)")
async def rank(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    target = user or interaction.user
    roles = [r for r in target.roles if r.name != "@everyone"]
    roles_text = ", ".join([r.mention for r in roles]) if roles else "Aucun"
    embed = discord.Embed(title=f"⭐ Profil de {target.name}", color=target.color)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Rôles/Rangs", value=roles_text, inline=False)
    embed.add_field(name="Rejoint le", value=target.joined_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Compte créé", value=target.created_at.strftime("%d/%m/%Y"), inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="addrank", description="➕ Ajouter un rôle à quelqu'un")
@app_commands.describe(user="Utilisateur", role="Rôle à ajouter")
@app_commands.checks.has_permissions(manage_roles=True)
async def addrank(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Tu ne peux pas donner un rôle supérieur au tien !", ephemeral=True)
        return
    await user.add_roles(role)
    await interaction.response.send_message(f"✅ {user.mention} a reçu le rôle {role.mention}")

@bot.tree.command(name="removerank", description="➖ Retirer un rôle")
@app_commands.describe(user="Utilisateur", role="Rôle à retirer")
@app_commands.checks.has_permissions(manage_roles=True)
async def removerank(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    if role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Tu ne peux pas retirer un rôle supérieur au tien !", ephemeral=True)
        return
    await user.remove_roles(role)
    await interaction.response.send_message(f"✅ Rôle {role.mention} retiré de {user.mention}")

# ==================== UTILITAIRES ====================
@bot.tree.command(name="clear", description="🧹 Supprimer des messages")
@app_commands.describe(amount="Nombre de messages (max 100)")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):
    if amount > 100:
        amount = 100
    await interaction.response.defer()
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🗑️ {len(deleted)} message(s) supprimé(s).", ephemeral=True)

@bot.tree.command(name="say", description="💬 Faire parler le bot")
@app_commands.describe(message="Message", channel="Salon (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def say(interaction: discord.Interaction, message: str, channel: Optional[discord.TextChannel] = None):
    target = channel or interaction.channel
    await target.send(message)
    await interaction.response.send_message("✅ Message envoyé !", ephemeral=True)

@bot.tree.command(name="help", description="❓ Voir les commandes")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Commandes du Bot", color=COLORS["info"])
    embed.add_field(name="🛡️ Protection", value="/protect @user\n/unprotect @user\n/protected", inline=False)
    embed.add_field(name="🔨 Modération", value="/ban /kick /mute /unmute\n/warn /warns /clearwarns /clear", inline=False)
    embed.add_field(name="⭐ Rangs", value="/rank /addrank /removerank", inline=False)
    embed.add_field(name="💬 Utilitaires", value="/say /help", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== ERREURS ====================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Tu n'as pas les permissions nécessaires !", ephemeral=True)
    elif isinstance(error, app_commands.BotMissingPermissions):
        await interaction.response.send_message("❌ Je n'ai pas les permissions nécessaires !", ephemeral=True)
    else:
        print(f"Erreur: {error}")

# ==================== LANCEMENT ====================
if __name__ == "__main__":
    bot.run(TOKEN)
