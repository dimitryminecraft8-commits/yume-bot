import discord
from discord.ext import commands
from discord import app_commands
import json
import os

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TOKEN")
DATA_FILE = "welcome_data.json"

COLORS = {
    "success": discord.Color.green(),
    "error": discord.Color.red(),
    "warn": discord.Color.orange(),
    "info": discord.Color.blue(),
}

# ==================== INITIALISATION ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="?", intents=intents)

data = {
    "welcome_channel": {},
    "bye_channel": {},
    "boost_channel": {},
    "staff_role": {},
}

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

load_data()

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"✅ Welcome Bot connecté: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"📊 {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur sync: {e}")

@bot.event
async def on_member_join(member):
    guild_id = str(member.guild.id)
    if guild_id not in data["welcome_channel"]:
        return
    channel = member.guild.get_channel(int(data["welcome_channel"][guild_id]))
    if not channel:
        return
    embed = discord.Embed(
        title="✨ Bienvenue sur 𝐘𝐮𝐦𝐞 !",
        description=(
            f"Bienvenue sur **𝐘𝐮𝐦𝐞**, {member.mention} !\n\n"
            f"Nous sommes ravis de t'accueillir parmi nous. "
            f"Prends le temps de découvrir le serveur, de lire le règlement "
            f"et de venir discuter avec la communauté. "
            f"Nous te souhaitons un agréable moment sur le serveur ! 🌸"
        ),
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Membre #{member.guild.member_count}")
    embed.timestamp = discord.utils.utcnow()
    await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    guild_id = str(member.guild.id)
    if guild_id not in data["bye_channel"]:
        return
    channel = member.guild.get_channel(int(data["bye_channel"][guild_id]))
    if not channel:
        return
    embed = discord.Embed(
        title="🌙 Au revoir...",
        description=(
            f"Au revoir **{member.name}** 🌙…\n\n"
            f"C'est toujours un peu triste de voir quelqu'un partir de **𝐘𝐮𝐦𝐞**\n"
            f"Merci pour les moments partagés, même les plus simples.\n"
            f"Chaque membre laisse une trace, et la tienne restera ici\n\n"
            f"Prends soin de toi… et sache que tu seras toujours le/la bienvenu(e) si tu reviens un jour 💜"
        ),
        color=discord.Color.dark_purple()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Il reste {member.guild.member_count} membres")
    embed.timestamp = discord.utils.utcnow()
    await channel.send(embed=embed)

@bot.event
async def on_member_update(before, after):
    guild_id = str(after.guild.id)
    if guild_id not in data["boost_channel"]:
        return
    if after.premium_since and not before.premium_since:
        channel = after.guild.get_channel(int(data["boost_channel"][guild_id]))
        if not channel:
            return
        embed = discord.Embed(
            title="💜 Merci pour le boost !",
            description=(
                f"Merci pour le boost, {after.mention} !\n\n"
                f"Ça fait vraiment plaisir, merci pour ton soutien à **𝐘𝐮𝐦𝐞** 💜\n"
                f"On apprécie énormément !"
            ),
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=after.display_avatar.url)
        embed.set_footer(text=f"Booster #{after.guild.premium_subscription_count}")
        embed.timestamp = discord.utils.utcnow()
        await channel.send(embed=embed)

# ==================== COMMANDES ====================
@bot.tree.command(name="setwelcome", description="📌 Définir le salon de bienvenue")
@app_commands.describe(channel="Salon où envoyer les messages de bienvenue")
@app_commands.checks.has_permissions(administrator=True)
async def setwelcome(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    data["welcome_channel"][guild_id] = str(channel.id)
    save_data()
    embed = discord.Embed(title="✅ Salon de bienvenue configuré", description=f"Messages de bienvenue dans {channel.mention}", color=COLORS["success"])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="setbye", description="🌙 Définir le salon d'au revoir")
@app_commands.describe(channel="Salon où envoyer les messages d'au revoir")
@app_commands.checks.has_permissions(administrator=True)
async def setbye(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    data["bye_channel"][guild_id] = str(channel.id)
    save_data()
    embed = discord.Embed(title="✅ Salon d'au revoir configuré", description=f"Messages d'au revoir dans {channel.mention}", color=COLORS["success"])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="setboost", description="💜 Définir le salon pour les boosts")
@app_commands.describe(channel="Salon où envoyer les messages de boost")
@app_commands.checks.has_permissions(administrator=True)
async def setboost(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    data["boost_channel"][guild_id] = str(channel.id)
    save_data()
    embed = discord.Embed(title="✅ Salon de boost configuré", description=f"Messages de boost dans {channel.mention}", color=COLORS["success"])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="setstaff", description="👮 Définir le rôle staff pour les DMs")
@app_commands.describe(role="Rôle staff")
@app_commands.checks.has_permissions(administrator=True)
async def setstaff(interaction: discord.Interaction, role: discord.Role):
    guild_id = str(interaction.guild.id)
    data["staff_role"][guild_id] = str(role.id)
    save_data()
    embed = discord.Embed(title="✅ Rôle staff configuré", description=f"Le rôle staff est {role.mention}", color=COLORS["success"])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="dmall", description="📨 Envoyer un DM à tous les membres")
@app_commands.describe(message="Message à envoyer")
@app_commands.checks.has_permissions(administrator=True)
async def dmall(interaction: discord.Interaction, message: str):
    await interaction.response.defer(ephemeral=True)
    success = 0
    failed = 0
    embed = discord.Embed(title=f"📨 Message de **{interaction.guild.name}**", description=message, color=discord.Color.purple())
    embed.set_footer(text=f"Envoyé par {interaction.user.name}")
    for member in interaction.guild.members:
        if member.bot:
            continue
        try:
            await member.send(embed=embed)
            success += 1
        except:
            failed += 1
    result = discord.Embed(title="📨 DM All terminé", description=f"✅ Envoyé à **{success}** membres\n❌ Échec pour **{failed}** membres", color=COLORS["success"])
    await interaction.followup.send(embed=result, ephemeral=True)

@bot.tree.command(name="dmstaff", description="👮 Envoyer un DM aux membres staff")
@app_commands.describe(message="Message à envoyer au staff")
@app_commands.checks.has_permissions(administrator=True)
async def dmstaff(interaction: discord.Interaction, message: str):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["staff_role"]:
        await interaction.response.send_message("❌ Aucun rôle staff configuré ! Utilise `/setstaff` d'abord.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    staff_role = interaction.guild.get_role(int(data["staff_role"][guild_id]))
    if not staff_role:
        await interaction.followup.send("❌ Rôle staff introuvable !", ephemeral=True)
        return
    success = 0
    failed = 0
    embed = discord.Embed(title=f"👮 Message Staff de **{interaction.guild.name}**", description=message, color=discord.Color.gold())
    embed.set_footer(text=f"Envoyé par {interaction.user.name}")
    for member in staff_role.members:
        if member.bot:
            continue
        try:
            await member.send(embed=embed)
            success += 1
        except:
            failed += 1
    result = discord.Embed(title="👮 DM Staff terminé", description=f"✅ Envoyé à **{success}** membres staff\n❌ Échec pour **{failed}** membres", color=COLORS["success"])
    await interaction.followup.send(embed=result, ephemeral=True)

@bot.tree.command(name="testwelcome", description="🧪 Tester le message de bienvenue")
@app_commands.checks.has_permissions(administrator=True)
async def testwelcome(interaction: discord.Interaction):
    await on_member_join(interaction.user)
    await interaction.response.send_message("✅ Message de bienvenue envoyé !", ephemeral=True)

@bot.tree.command(name="testbye", description="🌙 Tester le message d'au revoir")
@app_commands.checks.has_permissions(administrator=True)
async def testbye(interaction: discord.Interaction):
    await on_member_remove(interaction.user)
    await interaction.response.send_message("✅ Message d'au revoir envoyé !", ephemeral=True)

@bot.tree.command(name="whelp", description="❓ Voir les commandes du bot")
async def whelp(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Commandes Welcome Bot", color=COLORS["info"])
    embed.add_field(name="⚙️ Configuration", value="/setwelcome #salon\n/setbye #salon\n/setboost #salon\n/setstaff @role", inline=False)
    embed.add_field(name="📨 DM", value="/dmall message\n/dmstaff message", inline=False)
    embed.add_field(name="🧪 Test", value="/testwelcome\n/testbye", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Tu n'as pas les permissions nécessaires !", ephemeral=True)
    else:
        print(f"Erreur: {error}")

if __name__ == "__main__":
    bot.run(TOKEN)