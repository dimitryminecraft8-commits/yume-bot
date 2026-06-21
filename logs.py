import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TOKEN")
DATA_FILE = "logs_data.json"

# ==================== INITIALISATION ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# {guild_id: {"vocal": id, "messages": id, "members": id, "roles": id, "server": id, "moderation": id}}
data = {"logs": {}}

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

load_data()

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

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"✅ Logs Bot connecté: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"📊 {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur sync: {e}")

# ---- VOCAL ----
@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild

    # Join voc
    if not before.channel and after.channel:
        embed = discord.Embed(
            description=f"🎙️ {member.mention} a **rejoint** le vocal {after.channel.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        await send_log(guild, "vocal", embed)

    # Leave voc
    elif before.channel and not after.channel:
        embed = discord.Embed(
            description=f"🎙️ {member.mention} a **quitté** le vocal {before.channel.mention}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        await send_log(guild, "vocal", embed)

    # Move voc
    elif before.channel and after.channel and before.channel.id != after.channel.id:
        embed = discord.Embed(
            description=f"🎙️ {member.mention} est passé de {before.channel.mention} à {after.channel.mention}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        await send_log(guild, "vocal", embed)

# ---- MESSAGES ----
@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    embed = discord.Embed(
        title="🗑️ Message supprimé",
        description=f"**Auteur:** {message.author.mention}\n**Salon:** {message.channel.mention}\n**Contenu:**\n{message.content[:1000] if message.content else '*(aucun texte)*'}",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
    await send_log(message.guild, "messages", embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild:
        return
    if before.content == after.content:
        return
    embed = discord.Embed(
        title="✏️ Message modifié",
        description=f"**Auteur:** {before.author.mention}\n**Salon:** {before.channel.mention}",
        color=discord.Color.orange(),
        timestamp=datetime.now()
    )
    embed.add_field(name="Avant", value=before.content[:500] if before.content else "*(vide)*", inline=False)
    embed.add_field(name="Après", value=after.content[:500] if after.content else "*(vide)*", inline=False)
    embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
    await send_log(before.guild, "messages", embed)

# ---- MEMBRES ----
@bot.event
async def on_member_join(member):
    embed = discord.Embed(
        title="📥 Membre rejoint",
        description=f"{member.mention} a rejoint le serveur\n**Compte créé:** {member.created_at.strftime('%d/%m/%Y')}",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    embed.set_footer(text=f"Membre #{member.guild.member_count}")
    await send_log(member.guild, "members", embed)

@bot.event
async def on_member_remove(member):
    embed = discord.Embed(
        title="📤 Membre parti",
        description=f"{member.mention} ({member.name}) a quitté le serveur",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
    await send_log(member.guild, "members", embed)

# ---- RÔLES ----
@bot.event
async def on_member_update(before, after):
    # Changement de rôles
    added = set(after.roles) - set(before.roles)
    removed = set(before.roles) - set(after.roles)

    for role in added:
        embed = discord.Embed(
            description=f"🎭 {after.mention} a reçu le rôle {role.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        await send_log(after.guild, "roles", embed)

    for role in removed:
        embed = discord.Embed(
            description=f"🎭 {after.mention} a perdu le rôle {role.mention}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        await send_log(after.guild, "roles", embed)

# ---- SERVEUR (salons) ----
@bot.event
async def on_guild_channel_create(channel):
    embed = discord.Embed(
        title="➕ Salon créé",
        description=f"**Nom:** {channel.name}\n**Type:** {channel.type}",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    await send_log(channel.guild, "server", embed)

@bot.event
async def on_guild_channel_delete(channel):
    embed = discord.Embed(
        title="➖ Salon supprimé",
        description=f"**Nom:** {channel.name}\n**Type:** {channel.type}",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    await send_log(channel.guild, "server", embed)

# ---- MODÉRATION ----
@bot.event
async def on_member_ban(guild, user):
    embed = discord.Embed(
        title="🔨 Membre banni",
        description=f"{user.mention} ({user.name}) a été banni",
        color=discord.Color.dark_red(),
        timestamp=datetime.now()
    )
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    await send_log(guild, "moderation", embed)

@bot.event
async def on_member_unban(guild, user):
    embed = discord.Embed(
        title="🔓 Membre débanni",
        description=f"{user.mention} ({user.name}) a été débanni",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    embed.set_author(name=str(user), icon_url=user.display_avatar.url)
    await send_log(guild, "moderation", embed)

# ==================== COMMANDES ====================
@bot.tree.command(name="setlog", description="📋 Définir un salon de logs pour un type")
@app_commands.describe(type="Type de log", channel="Salon où envoyer ce type de log")
@app_commands.choices(type=[
    app_commands.Choice(name="🎙️ Vocal (join/leave/move)", value="vocal"),
    app_commands.Choice(name="💬 Messages (supprimés/modifiés)", value="messages"),
    app_commands.Choice(name="👤 Membres (join/leave serveur)", value="members"),
    app_commands.Choice(name="🎭 Rôles (ajout/retrait)", value="roles"),
    app_commands.Choice(name="⚙️ Serveur (salons)", value="server"),
    app_commands.Choice(name="🔨 Modération (ban/unban)", value="moderation"),
])
@app_commands.checks.has_permissions(administrator=True)
async def setlog(interaction: discord.Interaction, type: str, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["logs"]:
        data["logs"][guild_id] = {}
    data["logs"][guild_id][type] = str(channel.id)
    save_data()
    embed = discord.Embed(
        title="✅ Salon de logs configuré",
        description=f"Les logs **{type}** seront envoyés dans {channel.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="removelog", description="❌ Retirer un salon de logs")
@app_commands.describe(type="Type de log à retirer")
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
        await interaction.response.send_message(f"❌ Aucun salon configuré pour **{type}**.", ephemeral=True)

@bot.tree.command(name="setalllogs", description="🏗️ Configurer tous les logs dans un seul salon")
@app_commands.describe(channel="Salon où envoyer TOUS les logs")
@app_commands.checks.has_permissions(administrator=True)
async def setalllogs(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    data["logs"][guild_id] = {
        "vocal": str(channel.id),
        "messages": str(channel.id),
        "members": str(channel.id),
        "roles": str(channel.id),
        "server": str(channel.id),
        "moderation": str(channel.id),
    }
    save_data()
    embed = discord.Embed(
        title="✅ Tous les logs configurés",
        description=f"Tous les logs seront envoyés dans {channel.mention}",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="logconfig", description="📋 Voir la configuration des logs")
@app_commands.checks.has_permissions(administrator=True)
async def logconfig(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["logs"] or not data["logs"][guild_id]:
        await interaction.response.send_message("❌ Aucun log configuré.", ephemeral=True)
        return

    embed = discord.Embed(title="📋 Configuration des Logs", color=discord.Color.blue())
    types = {
        "vocal": "🎙️ Vocal",
        "messages": "💬 Messages",
        "members": "👤 Membres",
        "roles": "🎭 Rôles",
        "server": "⚙️ Serveur",
        "moderation": "🔨 Modération"
    }
    for key, label in types.items():
        ch_id = data["logs"][guild_id].get(key)
        if ch_id:
            channel = interaction.guild.get_channel(int(ch_id))
            value = channel.mention if channel else "❌ Salon supprimé"
        else:
            value = "❌ Non configuré"
        embed.add_field(name=label, value=value, inline=True)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="loghelp", description="❓ Voir les commandes du bot logs")
async def loghelp(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Commandes Logs Bot", color=discord.Color.blue())
    embed.add_field(name="⚙️ Configuration",
        value="/setlog type #salon — Définir un salon par type\n/setalllogs #salon — Tout dans un seul salon\n/removelog type — Retirer un type\n/logconfig — Voir la config",
        inline=False)
    embed.add_field(name="📊 Types de logs",
        value="🎙️ Vocal • 💬 Messages • 👤 Membres\n🎭 Rôles • ⚙️ Serveur • 🔨 Modération",
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