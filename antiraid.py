import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TOKEN")  # <-- Mets ton token ici
DATA_FILE = "antiraid_data.json"

# ==================== PARAMÈTRES ANTI-RAID ====================
# Nombre de joins en X secondes pour déclencher l'anti-raid
RAID_JOIN_COUNT = 5        # 5 personnes
RAID_JOIN_TIME = 10        # en 10 secondes

# Anti-spam
SPAM_MSG_COUNT = 5         # 5 messages
SPAM_MSG_TIME = 5          # en 5 secondes

# Anti-mention
MAX_MENTIONS = 5           # max 5 mentions par message

# ==================== COULEURS ====================
COLORS = {
    "success": discord.Color.green(),
    "error": discord.Color.red(),
    "warn": discord.Color.orange(),
    "info": discord.Color.blue(),
    "raid": discord.Color.dark_red()
}

# ==================== INITIALISATION ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="?", intents=intents)

# Données
data = {
    "settings": {},   # {guild_id: {"log_channel": id, "antiraid": True, "antispam": True, "antilinks": True, "antimentions": True, "antibots": True}}
    "whitelist": {},  # {guild_id: [user_ids]} utilisateurs exemptés
}

# Variables en mémoire
join_tracker = defaultdict(list)       # {guild_id: [timestamps]}
spam_tracker = defaultdict(lambda: defaultdict(list))  # {guild_id: {user_id: [timestamps]}}
lockdown_status = {}                   # {guild_id: bool}

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, default=str)

def get_settings(guild_id):
    gid = str(guild_id)
    if gid not in data["settings"]:
        data["settings"][gid] = {
            "log_channel": None,
            "antiraid": True,
            "antispam": True,
            "antilinks": True,
            "antimentions": True,
            "antibots": True
        }
        save_data()
    return data["settings"][gid]

load_data()

# ==================== LOGS ====================
async def send_log(guild, title, description, color, fields=None):
    settings = get_settings(guild.id)
    if not settings["log_channel"]:
        return
    channel = guild.get_channel(int(settings["log_channel"]))
    if not channel:
        return
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now())
    if fields:
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=True)
    embed.set_footer(text="AntiRaid Bot")
    await channel.send(embed=embed)

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"✅ AntiRaid Bot connecté: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"📊 {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur sync: {e}")

# ==================== ANTI-RAID (joins massifs) ====================
@bot.event
async def on_member_join(member):
    guild = member.guild
    guild_id = str(guild.id)
    settings = get_settings(guild.id)

    # Anti-bot
    if settings["antibots"] and member.bot:
        # Vérifier si le bot a été ajouté par un admin via logs
        await asyncio.sleep(1)
        authorized = False
        async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.bot_add):
            if entry.target.id == member.id:
                # Vérifier si c'est un admin
                if entry.user.guild_permissions.administrator:
                    authorized = True
                break
        if not authorized:
            try:
                await member.kick(reason="🛡️ AntiRaid - Bot non autorisé")
                await send_log(guild, "🤖 BOT KICKÉ", f"{member.mention} ({member.name}) a été kické automatiquement.",
                    COLORS["raid"], {"Raison": "Bot ajouté sans autorisation admin"})
            except:
                pass
        return

    # Anti-raid (joins massifs)
    if not settings["antiraid"]:
        return

    now = datetime.now()
    join_tracker[guild_id] = [t for t in join_tracker[guild_id] if (now - t).seconds < RAID_JOIN_TIME]
    join_tracker[guild_id].append(now)

    if len(join_tracker[guild_id]) >= RAID_JOIN_COUNT:
        # RAID DÉTECTÉ !
        join_tracker[guild_id] = []  # Reset

        if not lockdown_status.get(guild_id, False):
            await activate_lockdown(guild, reason="🚨 RAID DÉTECTÉ - Joins massifs")

# ==================== ANTI-SPAM ====================
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    settings = get_settings(message.guild.id)

    # Vérifier whitelist
    if guild_id in data["whitelist"] and user_id in data["whitelist"][guild_id]:
        await bot.process_commands(message)
        return

    # Anti-spam
    if settings["antispam"]:
        now = datetime.now()
        spam_tracker[guild_id][user_id] = [
            t for t in spam_tracker[guild_id][user_id]
            if (now - t).seconds < SPAM_MSG_TIME
        ]
        spam_tracker[guild_id][user_id].append(now)

        if len(spam_tracker[guild_id][user_id]) >= SPAM_MSG_COUNT:
            spam_tracker[guild_id][user_id] = []
            try:
                # Timeout 5 minutes
                await message.author.timeout(timedelta(minutes=5), reason="🛡️ Anti-spam")
                await message.channel.send(f"⚠️ {message.author.mention} a été timeout pour spam !", delete_after=5)
                await send_log(message.guild, "🚫 SPAM DÉTECTÉ",
                    f"{message.author.mention} a été timeout 5 minutes pour spam.",
                    COLORS["warn"], {"Salon": message.channel.mention, "Utilisateur": str(message.author)})
            except:
                pass

    # Anti-liens
    if settings["antilinks"]:
        links = ["http://", "https://", "discord.gg/", "discord.com/invite/"]
        if any(link in message.content.lower() for link in links):
            # Vérifier si l'auteur a la permission
            if not message.author.guild_permissions.administrator:
                await message.delete()
                await message.channel.send(f"🔗 {message.author.mention} les liens ne sont pas autorisés !", delete_after=5)
                await send_log(message.guild, "🔗 LIEN BLOQUÉ",
                    f"{message.author.mention} a tenté d'envoyer un lien.",
                    COLORS["warn"], {"Salon": message.channel.mention, "Message": message.content[:100]})
                return

    # Anti-mentions abusives
    if settings["antimentions"]:
        mention_count = len(message.mentions) + len(message.role_mentions)
        if message.mention_everyone:
            mention_count += 1
        if mention_count >= MAX_MENTIONS:
            if not message.author.guild_permissions.administrator:
                await message.delete()
                try:
                    await message.author.timeout(timedelta(minutes=10), reason="🛡️ Anti-mention spam")
                    await message.channel.send(f"⚠️ {message.author.mention} timeout pour mention spam !", delete_after=5)
                    await send_log(message.guild, "📢 MENTION SPAM",
                        f"{message.author.mention} a été timeout 10 minutes.",
                        COLORS["raid"], {"Mentions": str(mention_count), "Salon": message.channel.mention})
                except:
                    pass
                return

    await bot.process_commands(message)

# ==================== LOCKDOWN ====================
async def activate_lockdown(guild, reason="Lockdown activé"):
    guild_id = str(guild.id)
    lockdown_status[guild_id] = True

    everyone = guild.default_role
    locked = []

    for channel in guild.text_channels:
        try:
            overwrite = channel.overwrites_for(everyone)
            overwrite.send_messages = False
            await channel.set_permissions(everyone, overwrite=overwrite)
            locked.append(channel.name)
        except:
            pass

    await send_log(guild, "🔒 LOCKDOWN ACTIVÉ", reason, COLORS["raid"],
        {"Salons verrouillés": str(len(locked)), "Raison": reason})

async def deactivate_lockdown(guild):
    guild_id = str(guild.id)
    lockdown_status[guild_id] = False

    everyone = guild.default_role
    unlocked = []

    for channel in guild.text_channels:
        try:
            overwrite = channel.overwrites_for(everyone)
            overwrite.send_messages = None
            await channel.set_permissions(everyone, overwrite=overwrite)
            unlocked.append(channel.name)
        except:
            pass

    await send_log(guild, "🔓 LOCKDOWN DÉSACTIVÉ", "Le serveur est de nouveau ouvert.", COLORS["success"],
        {"Salons déverrouillés": str(len(unlocked))})

# ==================== COMMANDES ====================

# --- Configuration ---
@bot.tree.command(name="setlogs", description="📋 Définir le salon de logs")
@app_commands.describe(channel="Salon où envoyer les logs")
@app_commands.checks.has_permissions(administrator=True)
async def setlogs(interaction: discord.Interaction, channel: discord.TextChannel):
    settings = get_settings(interaction.guild.id)
    settings["log_channel"] = str(channel.id)
    save_data()
    embed = discord.Embed(title="✅ Salon de logs configuré", description=f"Les logs seront envoyés dans {channel.mention}", color=COLORS["success"])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="config", description="⚙️ Voir la configuration actuelle")
@app_commands.checks.has_permissions(administrator=True)
async def config(interaction: discord.Interaction):
    settings = get_settings(interaction.guild.id)
    guild_id = str(interaction.guild.id)
    log_ch = interaction.guild.get_channel(int(settings["log_channel"])) if settings["log_channel"] else None

    embed = discord.Embed(title="⚙️ Configuration AntiRaid", color=COLORS["info"])
    embed.add_field(name="📋 Salon logs", value=log_ch.mention if log_ch else "❌ Non configuré", inline=False)
    embed.add_field(name="🚨 Anti-Raid", value="✅ Activé" if settings["antiraid"] else "❌ Désactivé", inline=True)
    embed.add_field(name="🚫 Anti-Spam", value="✅ Activé" if settings["antispam"] else "❌ Désactivé", inline=True)
    embed.add_field(name="🔗 Anti-Liens", value="✅ Activé" if settings["antilinks"] else "❌ Désactivé", inline=True)
    embed.add_field(name="📢 Anti-Mentions", value="✅ Activé" if settings["antimentions"] else "❌ Désactivé", inline=True)
    embed.add_field(name="🤖 Anti-Bots", value="✅ Activé" if settings["antibots"] else "❌ Désactivé", inline=True)
    embed.add_field(name="🔒 Lockdown", value="✅ Actif" if lockdown_status.get(str(interaction.guild.id), False) else "❌ Inactif", inline=True)

    whitelist_count = len(data["whitelist"].get(str(interaction.guild.id), []))
    embed.add_field(name="🛡️ Whitelist", value=f"{whitelist_count} utilisateur(s)", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="toggle", description="🔧 Activer/désactiver une protection")
@app_commands.describe(protection="Protection à modifier")
@app_commands.choices(protection=[
    app_commands.Choice(name="Anti-Raid", value="antiraid"),
    app_commands.Choice(name="Anti-Spam", value="antispam"),
    app_commands.Choice(name="Anti-Liens", value="antilinks"),
    app_commands.Choice(name="Anti-Mentions", value="antimentions"),
    app_commands.Choice(name="Anti-Bots", value="antibots"),
])
@app_commands.checks.has_permissions(administrator=True)
async def toggle(interaction: discord.Interaction, protection: str):
    settings = get_settings(interaction.guild.id)
    settings[protection] = not settings[protection]
    save_data()
    status = "✅ Activé" if settings[protection] else "❌ Désactivé"
    await interaction.response.send_message(f"🔧 **{protection}** est maintenant **{status}**")

# --- Lockdown ---
@bot.tree.command(name="lockdown", description="🔒 Verrouiller tous les salons")
@app_commands.describe(reason="Raison du lockdown")
@app_commands.checks.has_permissions(administrator=True)
async def lockdown_cmd(interaction: discord.Interaction, reason: str = "Sécurité"):
    await interaction.response.defer()
    await activate_lockdown(interaction.guild, reason)
    await interaction.followup.send("🔒 **Lockdown activé !** Tous les salons sont verrouillés.")

@bot.tree.command(name="unlockdown", description="🔓 Déverrouiller tous les salons")
@app_commands.checks.has_permissions(administrator=True)
async def unlockdown_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    await deactivate_lockdown(interaction.guild)
    await interaction.followup.send("🔓 **Lockdown désactivé !** Le serveur est de nouveau ouvert.")

# --- Whitelist ---
@bot.tree.command(name="whitelist", description="🛡️ Ajouter un utilisateur à la whitelist")
@app_commands.describe(user="Utilisateur à whitelister")
@app_commands.checks.has_permissions(administrator=True)
async def whitelist_add(interaction: discord.Interaction, user: discord.Member):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["whitelist"]:
        data["whitelist"][guild_id] = []
    if str(user.id) in data["whitelist"][guild_id]:
        await interaction.response.send_message(f"❌ {user.mention} est déjà dans la whitelist !", ephemeral=True)
        return
    data["whitelist"][guild_id].append(str(user.id))
    save_data()
    await interaction.response.send_message(f"✅ {user.mention} ajouté à la whitelist — il ne sera plus sanctionné par l'anti-spam/liens.")

@bot.tree.command(name="unwhitelist", description="❌ Retirer un utilisateur de la whitelist")
@app_commands.describe(user="Utilisateur à retirer")
@app_commands.checks.has_permissions(administrator=True)
async def whitelist_remove(interaction: discord.Interaction, user: discord.Member):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["whitelist"] or str(user.id) not in data["whitelist"][guild_id]:
        await interaction.response.send_message(f"❌ {user.mention} n'est pas dans la whitelist !", ephemeral=True)
        return
    data["whitelist"][guild_id].remove(str(user.id))
    save_data()
    await interaction.response.send_message(f"✅ {user.mention} retiré de la whitelist.")

@bot.tree.command(name="whitelistview", description="📋 Voir la whitelist")
@app_commands.checks.has_permissions(administrator=True)
async def whitelist_view(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["whitelist"] or len(data["whitelist"][guild_id]) == 0:
        await interaction.response.send_message("🛡️ La whitelist est vide.", ephemeral=True)
        return
    mentions = []
    for uid in data["whitelist"][guild_id]:
        member = interaction.guild.get_member(int(uid))
        mentions.append(f"🛡️ {member.mention}" if member else f"🛡️ <@{uid}>")
    embed = discord.Embed(title="🛡️ Whitelist", description="\n".join(mentions), color=COLORS["info"])
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Help ---
@bot.tree.command(name="arhelp", description="❓ Voir les commandes AntiRaid")
async def arhelp(interaction: discord.Interaction):
    embed = discord.Embed(title="🛡️ Commandes AntiRaid", color=COLORS["info"])
    embed.add_field(name="⚙️ Configuration",
        value="/setlogs #salon — Définir le salon de logs\n/config — Voir la config\n/toggle — Activer/désactiver une protection",
        inline=False)
    embed.add_field(name="🔒 Lockdown",
        value="/lockdown [raison] — Verrouiller tous les salons\n/unlockdown — Déverrouiller",
        inline=False)
    embed.add_field(name="🛡️ Whitelist",
        value="/whitelist @user — Ajouter\n/unwhitelist @user — Retirer\n/whitelistview — Voir la liste",
        inline=False)
    embed.add_field(name="🤖 Protections automatiques",
        value="• Anti-Raid (joins massifs)\n• Anti-Spam (messages rapides)\n• Anti-Liens\n• Anti-Mentions abusives\n• Anti-Bots non autorisés",
        inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== ERREURS ====================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Tu n'as pas les permissions nécessaires !", ephemeral=True)
    else:
        print(f"Erreur: {error}")

# ==================== LANCEMENT ====================
if __name__ == "__main__":
    bot.run(TOKEN)
