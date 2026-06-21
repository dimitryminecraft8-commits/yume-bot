import discord
from discord.ext import commands
from discord import app_commands
import os
import random
import asyncio
from typing import Optional

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TOKEN")

EMOJIS = [
    "🎆", "🎇", "✨", "🎉", "🎊", "🎈", "🎀", "🎁", "🌟", "⭐",
    "💫", "🔥", "🌈", "🌸", "🌺", "🌼", "🌻", "🍀", "🦋", "🐬",
    "🌙", "☀️", "⚡", "❄️", "💎", "🔮", "🎵", "🎶", "🎮", "🕹️",
    "🚀", "🛸", "🌌", "🪐", "💜", "💙", "💚", "💛", "🧡", "❤️",
    "🖤", "🤍", "🤎", "💗", "💖", "💝", "🎯", "🎲", "🃏", "🎰",
]

# ==================== INITIALISATION ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Setup Bot connecté: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"📊 {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur sync: {e}")

# ==================== CRÉATION VOCAUX ====================
@bot.tree.command(name="createvocals", description="🔊 Créer plusieurs salons vocaux numérotés")
@app_commands.describe(
    name="Nom de base (ex: Vocal, Private)",
    start="Numéro de départ (ex: 1)",
    end="Numéro de fin (ex: 50)",
    category="Catégorie où créer les vocaux (optionnel)",
    user_limit="Nombre max de membres par vocal (0 = illimité)",
    emoji="Mettre un emoji random devant le nom ?"
)
@app_commands.checks.has_permissions(administrator=True)
async def createvocals(
    interaction: discord.Interaction,
    name: str,
    start: int,
    end: int,
    category: Optional[discord.CategoryChannel] = None,
    user_limit: int = 0,
    emoji: bool = True
):
    if start > end:
        await interaction.response.send_message("❌ Le numéro de départ doit être inférieur au numéro de fin !", ephemeral=True)
        return

    total = end - start + 1
    if total > 300:
        await interaction.response.send_message("❌ Tu ne peux pas créer plus de 300 salons à la fois !", ephemeral=True)
        return

    await interaction.response.send_message(f"🔨 Création de **{total}** salon(s) vocaux en cours... Ça peut prendre un moment.", ephemeral=True)

    created = 0
    for i in range(start, end + 1):
        if emoji:
            chosen_emoji = random.choice(EMOJIS)
            channel_name = f"{chosen_emoji} {name} {i}"
        else:
            channel_name = f"{name} {i}"
        try:
            await interaction.guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=user_limit if user_limit > 0 else None
            )
            created += 1
            if created % 5 == 0:
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Erreur création: {e}")

    await interaction.followup.send(f"✅ **{created}** salon(s) vocaux créé(s) avec succès !", ephemeral=True)

# ==================== CRÉATION TEXTUELS ====================
@bot.tree.command(name="createtext", description="💬 Créer plusieurs salons textuels numérotés")
@app_commands.describe(
    name="Nom de base (ex: chat, salon)",
    start="Numéro de départ",
    end="Numéro de fin",
    category="Catégorie où créer (optionnel)",
    emoji="Mettre un emoji random devant le nom ?"
)
@app_commands.checks.has_permissions(administrator=True)
async def createtext(
    interaction: discord.Interaction,
    name: str,
    start: int,
    end: int,
    category: Optional[discord.CategoryChannel] = None,
    emoji: bool = True
):
    if start > end:
        await interaction.response.send_message("❌ Le numéro de départ doit être inférieur au numéro de fin !", ephemeral=True)
        return

    total = end - start + 1
    if total > 300:
        await interaction.response.send_message("❌ Tu ne peux pas créer plus de 300 salons à la fois !", ephemeral=True)
        return

    await interaction.response.send_message(f"🔨 Création de **{total}** salon(s) textuels en cours...", ephemeral=True)

    created = 0
    for i in range(start, end + 1):
        if emoji:
            chosen_emoji = random.choice(EMOJIS)
            channel_name = f"{chosen_emoji}-{name}-{i}"
        else:
            channel_name = f"{name}-{i}"
        try:
            await interaction.guild.create_text_channel(name=channel_name, category=category)
            created += 1
            if created % 5 == 0:
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Erreur création: {e}")

    await interaction.followup.send(f"✅ **{created}** salon(s) textuels créé(s) avec succès !", ephemeral=True)

# ==================== CRÉATION CATÉGORIE ====================
@bot.tree.command(name="createcategory", description="📁 Créer une catégorie")
@app_commands.describe(
    name="Nom de la catégorie",
    staff_only="Visible seulement par un rôle ? (optionnel)"
)
@app_commands.checks.has_permissions(administrator=True)
async def createcategory(
    interaction: discord.Interaction,
    name: str,
    staff_only: Optional[discord.Role] = None
):
    await interaction.response.defer(ephemeral=True)
    overwrites = {}
    if staff_only:
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            staff_only: discord.PermissionOverwrite(view_channel=True)
        }
    try:
        category = await interaction.guild.create_category(name=name, overwrites=overwrites)
        msg = f"✅ Catégorie **{category.name}** créée !"
        if staff_only:
            msg += f"\n🔒 Visible seulement par {staff_only.mention}"
        await interaction.followup.send(msg, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

# ==================== SUPPRIMER VOCAUX ====================
@bot.tree.command(name="deletevocals", description="🗑️ Supprimer tous les vocaux d'une catégorie")
@app_commands.describe(category="Catégorie dont supprimer les vocaux")
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

# ==================== SUPPRIMER TEXTUELS ====================
@bot.tree.command(name="deletetext", description="🗑️ Supprimer tous les salons textuels d'une catégorie")
@app_commands.describe(category="Catégorie dont supprimer les salons texte")
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

# ==================== SETUP COMPLET ====================
@bot.tree.command(name="setupserver", description="🏗️ Créer une catégorie avec des vocaux d'un coup")
@app_commands.describe(
    category_name="Nom de la catégorie",
    vocal_name="Nom de base des vocaux (ex: Vocal)",
    count="Nombre de vocaux à créer",
    user_limit="Membres max par vocal (0 = illimité)",
    staff_only="Catégorie réservée à un rôle ? (optionnel)"
)
@app_commands.checks.has_permissions(administrator=True)
async def setupserver(
    interaction: discord.Interaction,
    category_name: str,
    vocal_name: str,
    count: int,
    user_limit: int = 0,
    staff_only: Optional[discord.Role] = None
):
    if count > 300:
        await interaction.response.send_message("❌ Maximum 300 vocaux !", ephemeral=True)
        return

    await interaction.response.send_message(f"🏗️ Création de la catégorie **{category_name}** avec **{count}** vocaux...", ephemeral=True)

    overwrites = {}
    if staff_only:
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            staff_only: discord.PermissionOverwrite(view_channel=True)
        }

    try:
        category = await interaction.guild.create_category(name=category_name, overwrites=overwrites)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur création catégorie: {e}", ephemeral=True)
        return

    created = 0
    for i in range(1, count + 1):
        chosen_emoji = random.choice(EMOJIS)
        channel_name = f"{chosen_emoji} {vocal_name} {i}"
        try:
            await interaction.guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=user_limit if user_limit > 0 else None
            )
            created += 1
            if created % 5 == 0:
                await asyncio.sleep(1)
        except:
            pass

    await interaction.followup.send(f"✅ Catégorie **{category_name}** créée avec **{created}** vocaux !", ephemeral=True)

# ==================== HELP ====================
@bot.tree.command(name="setuphelp", description="❓ Voir les commandes du bot setup")
async def setuphelp(interaction: discord.Interaction):
    embed = discord.Embed(title="🏗️ Commandes Setup Bot", color=discord.Color.blue())
    embed.add_field(name="🔊 Vocaux", value="/createvocals — Créer des vocaux de X à Y\n/deletevocals — Supprimer les vocaux d'une catégorie", inline=False)
    embed.add_field(name="💬 Textuels", value="/createtext — Créer des salons texte de X à Y\n/deletetext — Supprimer les salons texte d'une catégorie", inline=False)
    embed.add_field(name="📁 Catégories", value="/createcategory — Créer une catégorie\n/setupserver — Créer une catégorie + ses vocaux d'un coup", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== ERREURS ====================
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        try:
            await interaction.response.send_message("❌ Tu n'as pas les permissions nécessaires !", ephemeral=True)
        except:
            await interaction.followup.send("❌ Tu n'as pas les permissions nécessaires !", ephemeral=True)
    else:
        print(f"Erreur: {error}")

# ==================== LANCEMENT ====================
if __name__ == "__main__":
    bot.run(TOKEN)