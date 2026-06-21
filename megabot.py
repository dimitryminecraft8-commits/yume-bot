import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import random
import asyncio
from datetime import datetime, timedelta
from typing import Optional

# ==================== CONFIGURATION ====================
TOKEN = os.getenv("TOKEN")
DATA_FILE = "megabot_data.json"
PREFIX = "&"

# ==================== INITIALISATION ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

data = {
    "casino": {},          # {guild_id: {user_id: balance}}
    "casino_role": {},     # {guild_id: role_id}
    "daily": {},           # {guild_id: {user_id: last_claim}}
    "perms": {},           # {guild_id: {command: [role_ids]}}
    "absence_role": {},    # {guild_id: role_id}
    "absence_channel": {}, # {guild_id: channel_id}
    "absence_staff": {},   # {guild_id: role_id}
    "ticket_role": {},     # {guild_id: role_id}
    "ticket_category": {}, # {guild_id: category_id}
    "autorole": {},        # {guild_id: role_id}
    "laisse": {},          # {guild_id: {target_id: owner_id}}
    "laisse_role": {},     # {guild_id: role_id}
    "counters": {},        # {guild_id: {"members": id, "voice": id, "online": id}}
    "snipe": {},           # {channel_id: {content, author, time}}
    "blacklist": {},       # {guild_id: {user_id: raison}}
}

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

# ==================== SYSTÈME DE PERMISSIONS ====================
def has_perm(ctx, command_name):
    # Admins peuvent tout faire
    if ctx.author.guild_permissions.administrator:
        return True
    guild_id = str(ctx.guild.id)
    perms = data["perms"].get(guild_id, {}).get(command_name, [])
    if not perms:
        return False  # Si pas configuré, seuls les admins peuvent
    user_role_ids = [str(r.id) for r in ctx.author.roles]
    return any(rid in perms for rid in user_role_ids)

def perm_check(command_name):
    async def predicate(ctx):
        if has_perm(ctx, command_name):
            return True
        await ctx.send(f"❌ Tu n'as pas la permission d'utiliser cette commande !")
        return False
    return commands.check(predicate)

# ==================== CASINO HELPERS ====================
def get_balance(guild_id, user_id):
    return data["casino"].get(str(guild_id), {}).get(str(user_id), 0)

def set_balance(guild_id, user_id, amount):
    gid = str(guild_id)
    if gid not in data["casino"]:
        data["casino"][gid] = {}
    data["casino"][gid][str(user_id)] = max(0, amount)
    save_data()

def add_balance(guild_id, user_id, amount):
    set_balance(guild_id, user_id, get_balance(guild_id, user_id) + amount)

def has_casino_role(member):
    guild_id = str(member.guild.id)
    if member.guild_permissions.administrator:
        return True
    role_id = data["casino_role"].get(guild_id)
    if not role_id:
        return False
    return any(str(r.id) == role_id for r in member.roles)

# ==================== EVENTS ====================
@bot.event
async def on_ready():
    print(f"✅ MegaBot connecté: {bot.user}")
    print(f"ID: {bot.user.id}")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"📊 {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur sync: {e}")
    update_counters.start()

@bot.event
async def on_member_join(member):
    # Auto-role
    guild_id = str(member.guild.id)
    role_id = data["autorole"].get(guild_id)
    if role_id:
        role = member.guild.get_role(int(role_id))
        if role:
            try:
                await member.add_roles(role)
            except:
                pass

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    data["snipe"][str(message.channel.id)] = {
        "content": message.content,
        "author": str(message.author),
        "author_avatar": str(message.author.display_avatar.url),
        "time": datetime.now().isoformat()
    }

@bot.event
async def on_member_update(before, after):
    # Protection blacklist : retire automatiquement les rôles
    guild_id = str(after.guild.id)
    if guild_id in data["blacklist"] and str(after.id) in data["blacklist"][guild_id]:
        roles_to_remove = [r for r in after.roles if r.name != "@everyone"]
        if roles_to_remove:
            try:
                await after.remove_roles(*roles_to_remove, reason="Blacklist - roles retires automatiquement")
            except:
                pass

# ==================== LAISSE (suivre en vocal) ====================
@bot.event
async def on_voice_state_update(member, before, after):
    guild_id = str(member.guild.id)

    # Système de laisse
    if guild_id in data["laisse"] and str(member.id) in data["laisse"][guild_id]:
        owner_id = data["laisse"][guild_id][str(member.id)]
        owner = member.guild.get_member(int(owner_id))

        if owner and owner.voice and owner.voice.channel:
            # Si la personne en laisse n'est pas dans la même voc que son owner
            if not after.channel or after.channel.id != owner.voice.channel.id:
                try:
                    await member.move_to(owner.voice.channel)
                except:
                    pass

# ==================== COUNTERS (salons compteurs) ====================
@tasks.loop(minutes=5)
async def update_counters():
    for guild in bot.guilds:
        guild_id = str(guild.id)
        if guild_id not in data["counters"]:
            continue

        counters = data["counters"][guild_id]

        # Membres
        if "members" in counters:
            ch = guild.get_channel(int(counters["members"]))
            if ch:
                try:
                    await ch.edit(name=f"👥 Membres: {guild.member_count}")
                except:
                    pass

        # En vocal
        if "voice" in counters:
            ch = guild.get_channel(int(counters["voice"]))
            if ch:
                in_voice = sum(len(vc.members) for vc in guild.voice_channels)
                try:
                    await ch.edit(name=f"🎙️ En vocal: {in_voice}")
                except:
                    pass

        # En ligne
        if "online" in counters:
            ch = guild.get_channel(int(counters["online"]))
            if ch:
                online = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
                try:
                    await ch.edit(name=f"🟢 En ligne: {online}")
                except:
                    pass

# ==================== HELP ====================
class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        placeholder="📂 Choisis une catégorie...",
        options=[
            discord.SelectOption(label="Casino", emoji="🎰", description="Jeux de casino", value="casino"),
            discord.SelectOption(label="Tickets", emoji="🎫", description="Système de tickets", value="tickets"),
            discord.SelectOption(label="Modération", emoji="🔨", description="Commandes de modération", value="moderation"),
            discord.SelectOption(label="Absence", emoji="🌙", description="Demandes d'absence", value="absence"),
            discord.SelectOption(label="Vocal", emoji="🎙️", description="Commandes vocales", value="vocal"),
            discord.SelectOption(label="Fun", emoji="🎉", description="Commandes fun", value="fun"),
            discord.SelectOption(label="Utilitaire", emoji="🛠️", description="Outils divers", value="util"),
            discord.SelectOption(label="Config", emoji="⚙️", description="Configuration (admin)", value="config"),
        ]
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        cat = select.values[0]
        embeds = {
            "casino": discord.Embed(title="🎰 Casino", color=discord.Color.gold(), description=(
                "`&balance` — Voir ses jetons\n"
                "`&daily` — Jetons gratuits quotidiens\n"
                "`&blackjack <mise>` — Jouer au blackjack\n"
                "`&coinflip <mise> <pile/face>` — Pile ou face\n"
                "`&roulette <mise> <rouge/noir/numéro>` — Roulette\n"
                "`&slots <mise>` — Machine à sous\n"
                "`&give @user <montant>` — Donner des jetons\n"
                "`&leaderboard` — Classement des plus riches"
            )),
            "tickets": discord.Embed(title="🎫 Tickets", color=discord.Color.blue(), description=(
                "`/ticketsetup` — Créer le panel de tickets\n"
                "`+close` — Fermer un ticket (avec confirmation)\n"
                "`+rename <nom>` — Renommer le ticket\n"
                "`+add @user` — Ajouter quelqu'un au ticket\n"
                "`+remove @user` — Retirer quelqu'un du ticket"
            )),
            "moderation": discord.Embed(title="🔨 Modération", color=discord.Color.red(), description=(
                "`&clear <nombre>` — Supprimer des messages\n"
                "`&purgeuser @user <nombre>` — Supprimer les messages d'une personne\n"
                "`&untimeout @user` — Enlever un timeout\n"
                "`&slowmode <secondes>` — Mode lent\n"
                "`&lock` / `&unlock` — Verrouiller/déverrouiller\n"
                "`&hide` / `&unhide` — Cacher/montrer un salon\n"
                "`&nick @user <pseudo>` — Changer un pseudo\n"
                "`&bl @user <raison>` — Blacklist (retire les rôles, bloque)\n"
                "`&unbl @user` — Retirer la blacklist\n"
                "`&bllist` — Voir la liste des blacklist"
            )),
            "absence": discord.Embed(title="🌙 Absence", color=discord.Color.purple(), description=(
                "`/absence <raison> <date>` — Demander une absence\n"
                "Le staff accepte ou refuse via boutons"
            )),
            "vocal": discord.Embed(title="🎙️ Vocal", color=discord.Color.green(), description=(
                "`&laisse @user` — Mettre en laisse (suit ton vocal)\n"
                "`&unlaisse @user` — Retirer la laisse\n"
                "`&vkick @user` — Kick d'un vocal\n"
                "`&vmute @user` — Mute vocal\n"
                "`&drag @user` — Ramener dans ton vocal"
            )),
            "fun": discord.Embed(title="🎉 Fun", color=discord.Color.magenta(), description=(
                "`&hug @user` — Faire un câlin\n"
                "`&kiss @user` — Faire un bisou\n"
                "`&pat @user` — Caresser\n"
                "`&ship @user1 @user2` — Compatibilité amoureuse\n"
                "`&8ball <question>` — Boule magique\n"
                "`&say <message>` — Faire parler le bot"
            )),
            "util": discord.Embed(title="🛠️ Utilitaire", color=discord.Color.teal(), description=(
                "`&poll <question>` — Sondage rapide\n"
                "`/giveaway` — Lancer un giveaway\n"
                "`&remind <temps> <rappel>` — Rappel\n"
                "`&snipe` — Dernier message supprimé\n"
                "`&av @user` — Voir l'avatar\n"
                "`&userinfo @user` — Infos membre\n"
                "`&serverinfo` — Infos serveur\n"
                "`&membercount` — Stats du serveur"
            )),
            "config": discord.Embed(title="⚙️ Configuration (Admin)", color=discord.Color.dark_grey(), description=(
                "`/setperm <commande> <roles>` — Définir qui peut utiliser une commande\n"
                "`/removeperm <commande>` — Retirer les perms\n"
                "`/permlist` — Voir les permissions\n"
                "`/setcasino <role>` — Rôle casino\n"
                "`/setautorole <role>` — Rôle auto à l'arrivée\n"
                "`/setlaisserole <role>` — Rôle qui peut faire &laisse\n"
                "`/setabsence <role_donné> <salon> <role_staff>` — Config absence\n"
                "`/setticket <role> <catégorie>` — Config tickets\n"
                "`/setcounters` — Créer les salons compteurs\n"
                "`/reactionrole` — Créer un message à réactions"
            )),
        }
        await interaction.response.edit_message(embed=embeds[cat], view=self)

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="📚 Aide - MegaBot Yume",
        description="Sélectionne une catégorie dans le menu ci-dessous pour voir les commandes !",
        color=discord.Color.blurple()
    )
    embed.set_footer(text="MegaBot Yume • Tout-en-un")
    await ctx.send(embed=embed, view=HelpView())

# ==================== CASINO ====================
@bot.command(name="balance", aliases=["bal"])
async def balance(ctx, member: discord.Member = None):
    if not has_casino_role(ctx.author):
        await ctx.send("❌ Tu n'as pas accès au casino !")
        return
    target = member or ctx.author
    bal = get_balance(ctx.guild.id, target.id)
    embed = discord.Embed(title=f"🎰 Jetons de {target.name}", description=f"💰 **{bal}** jetons", color=discord.Color.gold())
    await ctx.send(embed=embed)

@bot.command(name="daily")
async def daily(ctx):
    if not has_casino_role(ctx.author):
        await ctx.send("❌ Tu n'as pas accès au casino !")
        return
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)
    if guild_id not in data["daily"]:
        data["daily"][guild_id] = {}
    last = data["daily"][guild_id].get(user_id)
    now = datetime.now()
    if last:
        last_time = datetime.fromisoformat(last)
        if (now - last_time).total_seconds() < 86400:
            remaining = 86400 - (now - last_time).total_seconds()
            hours = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            await ctx.send(f"⏳ Tu as déjà récupéré ton daily ! Reviens dans **{hours}h {mins}m**")
            return
    reward = 500
    add_balance(ctx.guild.id, ctx.author.id, reward)
    data["daily"][guild_id][user_id] = now.isoformat()
    save_data()
    await ctx.send(f"✅ Tu as reçu **{reward}** jetons ! 💰 Nouveau solde: **{get_balance(ctx.guild.id, ctx.author.id)}**")

@bot.command(name="blackjack", aliases=["bj"])
async def blackjack(ctx, mise: int):
    if not has_casino_role(ctx.author):
        await ctx.send("❌ Tu n'as pas accès au casino !")
        return
    if mise <= 0:
        await ctx.send("❌ Mise invalide !")
        return
    if get_balance(ctx.guild.id, ctx.author.id) < mise:
        await ctx.send("❌ Tu n'as pas assez de jetons !")
        return

    def draw():
        return random.randint(1, 11)

    player = [draw(), draw()]
    dealer = [draw(), draw()]

    def total(cards):
        return sum(cards)

    # Dealer joue
    while total(dealer) < 17:
        dealer.append(draw())

    p_total = total(player)
    d_total = total(dealer)

    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.gold())
    embed.add_field(name="Tes cartes", value=f"{player} = **{p_total}**", inline=False)
    embed.add_field(name="Cartes du croupier", value=f"{dealer} = **{d_total}**", inline=False)

    if p_total > 21:
        add_balance(ctx.guild.id, ctx.author.id, -mise)
        embed.description = f"💥 Tu as dépassé 21 ! Tu perds **{mise}** jetons."
        embed.color = discord.Color.red()
    elif d_total > 21 or p_total > d_total:
        add_balance(ctx.guild.id, ctx.author.id, mise)
        embed.description = f"🎉 Tu gagnes **{mise}** jetons !"
        embed.color = discord.Color.green()
    elif p_total == d_total:
        embed.description = "🤝 Égalité ! Tu récupères ta mise."
    else:
        add_balance(ctx.guild.id, ctx.author.id, -mise)
        embed.description = f"😢 Le croupier gagne. Tu perds **{mise}** jetons."
        embed.color = discord.Color.red()

    embed.set_footer(text=f"Solde: {get_balance(ctx.guild.id, ctx.author.id)} jetons")
    await ctx.send(embed=embed)

@bot.command(name="coinflip", aliases=["cf"])
async def coinflip(ctx, mise: int, choix: str):
    if not has_casino_role(ctx.author):
        await ctx.send("❌ Tu n'as pas accès au casino !")
        return
    if choix.lower() not in ["pile", "face"]:
        await ctx.send("❌ Choisis **pile** ou **face** !")
        return
    if mise <= 0 or get_balance(ctx.guild.id, ctx.author.id) < mise:
        await ctx.send("❌ Mise invalide ou solde insuffisant !")
        return

    result = random.choice(["pile", "face"])
    embed = discord.Embed(title="🪙 Pile ou Face", color=discord.Color.gold())
    if result == choix.lower():
        add_balance(ctx.guild.id, ctx.author.id, mise)
        embed.description = f"🎉 C'est **{result}** ! Tu gagnes **{mise}** jetons !"
        embed.color = discord.Color.green()
    else:
        add_balance(ctx.guild.id, ctx.author.id, -mise)
        embed.description = f"😢 C'est **{result}**. Tu perds **{mise}** jetons."
        embed.color = discord.Color.red()
    embed.set_footer(text=f"Solde: {get_balance(ctx.guild.id, ctx.author.id)} jetons")
    await ctx.send(embed=embed)

@bot.command(name="roulette")
async def roulette(ctx, mise: int, choix: str):
    if not has_casino_role(ctx.author):
        await ctx.send("❌ Tu n'as pas accès au casino !")
        return
    if mise <= 0 or get_balance(ctx.guild.id, ctx.author.id) < mise:
        await ctx.send("❌ Mise invalide ou solde insuffisant !")
        return

    number = random.randint(0, 36)
    color = "vert" if number == 0 else ("rouge" if number % 2 == 1 else "noir")

    embed = discord.Embed(title="🎡 Roulette", color=discord.Color.gold())
    embed.add_field(name="Résultat", value=f"**{number}** ({color})", inline=False)

    won = False
    multiplier = 0
    if choix.lower() in ["rouge", "noir", "vert"]:
        if choix.lower() == color:
            won = True
            multiplier = 35 if color == "vert" else 2
    elif choix.isdigit():
        if int(choix) == number:
            won = True
            multiplier = 36

    if won:
        gain = mise * multiplier
        add_balance(ctx.guild.id, ctx.author.id, gain - mise)
        embed.description = f"🎉 Tu gagnes **{gain}** jetons !"
        embed.color = discord.Color.green()
    else:
        add_balance(ctx.guild.id, ctx.author.id, -mise)
        embed.description = f"😢 Perdu ! Tu perds **{mise}** jetons."
        embed.color = discord.Color.red()
    embed.set_footer(text=f"Solde: {get_balance(ctx.guild.id, ctx.author.id)} jetons")
    await ctx.send(embed=embed)

@bot.command(name="slots")
async def slots(ctx, mise: int):
    if not has_casino_role(ctx.author):
        await ctx.send("❌ Tu n'as pas accès au casino !")
        return
    if mise <= 0 or get_balance(ctx.guild.id, ctx.author.id) < mise:
        await ctx.send("❌ Mise invalide ou solde insuffisant !")
        return

    symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]

    embed = discord.Embed(title="🎰 Machine à sous", description=f"# {' | '.join(result)}", color=discord.Color.gold())

    if result[0] == result[1] == result[2]:
        gain = mise * 10
        add_balance(ctx.guild.id, ctx.author.id, gain - mise)
        embed.add_field(name="🎉 JACKPOT !", value=f"Tu gagnes **{gain}** jetons !")
        embed.color = discord.Color.green()
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        gain = mise * 2
        add_balance(ctx.guild.id, ctx.author.id, gain - mise)
        embed.add_field(name="✨ Deux symboles !", value=f"Tu gagnes **{gain}** jetons !")
        embed.color = discord.Color.green()
    else:
        add_balance(ctx.guild.id, ctx.author.id, -mise)
        embed.add_field(name="😢 Perdu", value=f"Tu perds **{mise}** jetons.")
        embed.color = discord.Color.red()
    embed.set_footer(text=f"Solde: {get_balance(ctx.guild.id, ctx.author.id)} jetons")
    await ctx.send(embed=embed)

@bot.command(name="give")
async def give(ctx, member: discord.Member, montant: int):
    if not has_casino_role(ctx.author):
        await ctx.send("❌ Tu n'as pas accès au casino !")
        return
    if montant <= 0 or get_balance(ctx.guild.id, ctx.author.id) < montant:
        await ctx.send("❌ Montant invalide ou solde insuffisant !")
        return
    add_balance(ctx.guild.id, ctx.author.id, -montant)
    add_balance(ctx.guild.id, member.id, montant)
    await ctx.send(f"✅ Tu as donné **{montant}** jetons à {member.mention} !")

@bot.command(name="leaderboard", aliases=["lb"])
async def leaderboard(ctx):
    guild_id = str(ctx.guild.id)
    if guild_id not in data["casino"] or not data["casino"][guild_id]:
        await ctx.send("❌ Personne n'a de jetons !")
        return
    sorted_users = sorted(data["casino"][guild_id].items(), key=lambda x: x[1], reverse=True)[:10]
    embed = discord.Embed(title="🏆 Classement Casino", color=discord.Color.gold())
    desc = ""
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, bal) in enumerate(sorted_users):
        member = ctx.guild.get_member(int(uid))
        name = member.name if member else "Inconnu"
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        desc += f"{medal} {name} — 💰 {bal} jetons\n"
    embed.description = desc
    await ctx.send(embed=embed)

# ==================== MODÉRATION ====================
@bot.command(name="clear")
@perm_check("clear")
async def clear(ctx, nombre: int):
    if nombre > 100:
        nombre = 100
    deleted = await ctx.channel.purge(limit=nombre + 1)
    msg = await ctx.send(f"🗑️ **{len(deleted)-1}** messages supprimés !")
    await asyncio.sleep(3)
    await msg.delete()

@bot.command(name="purgeuser")
@perm_check("purgeuser")
async def purgeuser(ctx, member: discord.Member, nombre: int):
    def check(m):
        return m.author.id == member.id
    deleted = await ctx.channel.purge(limit=nombre, check=check)
    msg = await ctx.send(f"🗑️ **{len(deleted)}** messages de {member.mention} supprimés !")
    await asyncio.sleep(3)
    await msg.delete()

@bot.command(name="untimeout")
@perm_check("untimeout")
async def untimeout(ctx, member: discord.Member):
    try:
        await member.timeout(None)
        await ctx.send(f"✅ Timeout retiré pour {member.mention} !")
    except:
        await ctx.send("❌ Impossible de retirer le timeout.")

@bot.command(name="slowmode")
@perm_check("slowmode")
async def slowmode(ctx, secondes: int):
    await ctx.channel.edit(slowmode_delay=secondes)
    if secondes == 0:
        await ctx.send("✅ Mode lent désactivé !")
    else:
        await ctx.send(f"✅ Mode lent réglé à **{secondes}** secondes !")

@bot.command(name="lock")
@perm_check("lock")
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Salon verrouillé !")

@bot.command(name="unlock")
@perm_check("lock")
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
    await ctx.send("🔓 Salon déverrouillé !")

@bot.command(name="hide")
@perm_check("hide")
async def hide(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=False)
    await ctx.send("👁️ Salon caché !")

@bot.command(name="unhide")
@perm_check("hide")
async def unhide(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=None)
    await ctx.send("👁️ Salon visible !")

@bot.command(name="nick")
@perm_check("nick")
async def nick(ctx, member: discord.Member, *, pseudo: str):
    try:
        await member.edit(nick=pseudo)
        await ctx.send(f"✅ Pseudo de {member.mention} changé en **{pseudo}** !")
    except:
        await ctx.send("❌ Impossible de changer le pseudo.")

@bot.command(name="bl")
@perm_check("bl")
async def blacklist_cmd(ctx, member: discord.Member, *, raison: str = "Aucune raison"):
    guild_id = str(ctx.guild.id)
    if guild_id not in data["blacklist"]:
        data["blacklist"][guild_id] = {}
    if str(member.id) in data["blacklist"][guild_id]:
        await ctx.send(f"❌ {member.mention} est déjà blacklist !")
        return
    roles_to_remove = [r for r in member.roles if r.name != "@everyone"]
    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason=f"Blacklist: {raison}")
        except:
            pass
    data["blacklist"][guild_id][str(member.id)] = raison
    save_data()
    await ctx.send(f"🚫 {member.mention} a été **blacklist**. Ses rôles ont été retirés et il ne pourra plus en recevoir.")

@bot.command(name="unbl")
@perm_check("bl")
async def unblacklist_cmd(ctx, member: discord.Member):
    guild_id = str(ctx.guild.id)
    if guild_id not in data["blacklist"] or str(member.id) not in data["blacklist"][guild_id]:
        await ctx.send(f"❌ {member.mention} n'est pas blacklist.")
        return
    del data["blacklist"][guild_id][str(member.id)]
    save_data()
    await ctx.send(f"✅ {member.mention} n'est plus blacklist. Il peut de nouveau recevoir des rôles.")

@bot.command(name="bllist")
@perm_check("bl")
async def bllist_cmd(ctx):
    guild_id = str(ctx.guild.id)
    if guild_id not in data["blacklist"] or not data["blacklist"][guild_id]:
        await ctx.send("✅ Aucune personne blacklist.")
        return
    embed = discord.Embed(title="🚫 Liste des Blacklist", color=discord.Color.dark_red())
    desc = ""
    for uid, raison in data["blacklist"][guild_id].items():
        member = ctx.guild.get_member(int(uid))
        name = member.mention if member else f"<@{uid}>"
        desc += f"{name} — *{raison}*\n"
    embed.description = desc
    await ctx.send(embed=embed)

# ==================== VOCAL ====================
@bot.command(name="laisse")
async def laisse(ctx, member: discord.Member):
    guild_id = str(ctx.guild.id)
    # Vérif permission (admin ou rôle laisse)
    is_admin = ctx.author.guild_permissions.administrator
    laisse_role_id = data["laisse_role"].get(guild_id)
    has_laisse_role = laisse_role_id and any(str(r.id) == laisse_role_id for r in ctx.author.roles)
    if not is_admin and not has_laisse_role:
        await ctx.send("❌ Tu n'as pas la permission d'utiliser la laisse !")
        return

    if guild_id not in data["laisse"]:
        data["laisse"][guild_id] = {}
    data["laisse"][guild_id][str(member.id)] = str(ctx.author.id)
    save_data()

    # Si l'owner est en voc, ramener la personne
    if ctx.author.voice and ctx.author.voice.channel:
        try:
            await member.move_to(ctx.author.voice.channel)
        except:
            pass

    await ctx.send(f"🦮 {member.mention} est maintenant en laisse ! Il te suivra partout en vocal 😈")

@bot.command(name="unlaisse")
async def unlaisse(ctx, member: discord.Member):
    guild_id = str(ctx.guild.id)
    if guild_id in data["laisse"] and str(member.id) in data["laisse"][guild_id]:
        del data["laisse"][guild_id][str(member.id)]
        save_data()
        await ctx.send(f"✅ {member.mention} n'est plus en laisse !")
    else:
        await ctx.send(f"❌ {member.mention} n'est pas en laisse.")

@bot.command(name="vkick")
@perm_check("vkick")
async def vkick(ctx, member: discord.Member):
    if member.voice:
        await member.move_to(None)
        await ctx.send(f"✅ {member.mention} a été kick du vocal !")
    else:
        await ctx.send("❌ Cette personne n'est pas en vocal.")

@bot.command(name="vmute")
@perm_check("vmute")
async def vmute(ctx, member: discord.Member):
    if member.voice:
        await member.edit(mute=not member.voice.mute)
        await ctx.send(f"✅ {member.mention} {'mute' if member.voice.mute else 'unmute'} !")
    else:
        await ctx.send("❌ Cette personne n'est pas en vocal.")

@bot.command(name="drag")
@perm_check("drag")
async def drag(ctx, member: discord.Member):
    if ctx.author.voice and ctx.author.voice.channel:
        try:
            await member.move_to(ctx.author.voice.channel)
            await ctx.send(f"✅ {member.mention} ramené dans ton vocal !")
        except:
            await ctx.send("❌ Impossible de déplacer cette personne.")
    else:
        await ctx.send("❌ Tu dois être dans un vocal !")

# ==================== FUN ====================
@bot.command(name="hug")
async def hug(ctx, member: discord.Member):
    await ctx.send(f"🤗 {ctx.author.mention} fait un gros câlin à {member.mention} !")

@bot.command(name="kiss")
async def kiss(ctx, member: discord.Member):
    await ctx.send(f"💋 {ctx.author.mention} fait un bisou à {member.mention} !")

@bot.command(name="pat")
async def pat(ctx, member: discord.Member):
    await ctx.send(f"😊 {ctx.author.mention} caresse la tête de {member.mention} !")

@bot.command(name="ship")
async def ship(ctx, member1: discord.Member, member2: discord.Member):
    percent = random.randint(0, 100)
    bar = "█" * (percent // 10) + "░" * (10 - percent // 10)
    await ctx.send(f"💕 **{member1.name}** x **{member2.name}**\n{bar} **{percent}%**")

@bot.command(name="8ball")
async def eightball(ctx, *, question: str):
    responses = ["Oui", "Non", "Peut-être", "Certainement", "Jamais", "Probablement", "Aucune chance", "Sans aucun doute"]
    await ctx.send(f"🎱 **Question:** {question}\n**Réponse:** {random.choice(responses)}")

@bot.command(name="say")
@perm_check("say")
async def say(ctx, *, message: str):
    await ctx.message.delete()
    await ctx.send(message)

# ==================== UTILITAIRE ====================
@bot.command(name="poll")
async def poll(ctx, *, question: str):
    embed = discord.Embed(title="📊 Sondage", description=question, color=discord.Color.blue())
    embed.set_footer(text=f"Sondage de {ctx.author.name}")
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")

@bot.command(name="snipe")
async def snipe(ctx):
    channel_id = str(ctx.channel.id)
    if channel_id not in data["snipe"]:
        await ctx.send("❌ Aucun message supprimé récemment.")
        return
    sniped = data["snipe"][channel_id]
    embed = discord.Embed(description=sniped["content"] or "*(aucun texte)*", color=discord.Color.orange())
    embed.set_author(name=sniped["author"], icon_url=sniped["author_avatar"])
    embed.set_footer(text="Message supprimé")
    await ctx.send(embed=embed)

@bot.command(name="av", aliases=["avatar"])
async def av(ctx, member: discord.Member = None):
    target = member or ctx.author
    embed = discord.Embed(title=f"Avatar de {target.name}", color=target.color)
    embed.set_image(url=target.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="userinfo")
async def userinfo(ctx, member: discord.Member = None):
    target = member or ctx.author
    embed = discord.Embed(title=f"Infos de {target.name}", color=target.color)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="ID", value=target.id, inline=True)
    embed.add_field(name="Compte créé", value=target.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="A rejoint", value=target.joined_at.strftime("%d/%m/%Y"), inline=True)
    roles = [r.mention for r in target.roles if r.name != "@everyone"]
    embed.add_field(name=f"Rôles ({len(roles)})", value=" ".join(roles[:10]) if roles else "Aucun", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="serverinfo")
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"Infos de {guild.name}", color=discord.Color.blue())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👥 Membres", value=guild.member_count, inline=True)
    embed.add_field(name="📅 Créé le", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="👑 Propriétaire", value=guild.owner.mention if guild.owner else "?", inline=True)
    embed.add_field(name="💬 Salons", value=len(guild.channels), inline=True)
    embed.add_field(name="🎭 Rôles", value=len(guild.roles), inline=True)
    embed.add_field(name="🚀 Boosts", value=guild.premium_subscription_count, inline=True)
    await ctx.send(embed=embed)

@bot.command(name="membercount")
async def membercount(ctx):
    guild = ctx.guild
    humans = sum(1 for m in guild.members if not m.bot)
    bots = sum(1 for m in guild.members if m.bot)
    online = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
    embed = discord.Embed(title=f"📊 Stats de {guild.name}", color=discord.Color.green())
    embed.add_field(name="Total", value=guild.member_count, inline=True)
    embed.add_field(name="Humains", value=humans, inline=True)
    embed.add_field(name="Bots", value=bots, inline=True)
    embed.add_field(name="En ligne", value=online, inline=True)
    await ctx.send(embed=embed)

@bot.command(name="remind")
async def remind(ctx, temps: str, *, rappel: str):
    # Parse temps (ex: 10m, 1h)
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        unit = temps[-1]
        amount = int(temps[:-1])
        seconds = amount * units[unit]
    except:
        await ctx.send("❌ Format invalide ! Ex: `&remind 10m Faire la vaisselle`")
        return
    await ctx.send(f"⏰ Rappel programmé dans **{temps}** !")
    await asyncio.sleep(seconds)
    await ctx.send(f"⏰ {ctx.author.mention} Rappel: **{rappel}**")

# ==================== TICKETS ====================
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ouvrir un ticket", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        # Vérifier si la personne a déjà un ticket
        existing = discord.utils.get(interaction.guild.channels, name=f"ticket-{interaction.user.name.lower()}")
        if existing:
            await interaction.response.send_message(f"❌ Tu as déjà un ticket: {existing.mention}", ephemeral=True)
            return

        # Permissions
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        ticket_role_id = data["ticket_role"].get(guild_id)
        if ticket_role_id:
            role = interaction.guild.get_role(int(ticket_role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        category = None
        cat_id = data["ticket_category"].get(guild_id)
        if cat_id:
            category = interaction.guild.get_channel(int(cat_id))

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites,
            category=category
        )

        embed = discord.Embed(
            title="🎫 Ticket ouvert",
            description=f"Bienvenue {interaction.user.mention} !\nUn membre du staff va te répondre.\n\n`+close` — Fermer\n`+rename <nom>` — Renommer\n`+add @user` — Ajouter\n`+remove @user` — Retirer",
            color=discord.Color.green()
        )
        await channel.send(embed=embed)
        await interaction.response.send_message(f"✅ Ton ticket: {channel.mention}", ephemeral=True)

@bot.command(name="close")
async def close_ticket(ctx):
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ Cette commande s'utilise dans un ticket !")
        return

    embed = discord.Embed(title="⚠️ Confirmation", description="Es-tu sûr de vouloir fermer ce ticket ?", color=discord.Color.orange())

    class ConfirmView(discord.ui.View):
        @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message("🔒 Fermeture du ticket dans 5 secondes...")
            await asyncio.sleep(5)
            await ctx.channel.delete()

        @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message("❌ Fermeture annulée.")

    await ctx.send(embed=embed, view=ConfirmView())

@bot.command(name="rename")
async def rename_ticket(ctx, *, nom: str):
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ Cette commande s'utilise dans un ticket !")
        return
    await ctx.channel.edit(name=f"ticket-{nom}")
    await ctx.send(f"✅ Ticket renommé en **ticket-{nom}** !")

@bot.command(name="add")
async def add_ticket(ctx, member: discord.Member):
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ Cette commande s'utilise dans un ticket !")
        return
    await ctx.channel.set_permissions(member, view_channel=True, send_messages=True)
    await ctx.send(f"✅ {member.mention} ajouté au ticket !")

@bot.command(name="remove")
async def remove_ticket(ctx, member: discord.Member):
    if not ctx.channel.name.startswith("ticket-"):
        await ctx.send("❌ Cette commande s'utilise dans un ticket !")
        return
    await ctx.channel.set_permissions(member, overwrite=None)
    await ctx.send(f"✅ {member.mention} retiré du ticket !")

# ==================== SLASH: TICKET SETUP ====================
@bot.tree.command(name="ticketsetup", description="🎫 Créer le panel de tickets")
@app_commands.describe(channel="Salon où mettre le panel")
@app_commands.checks.has_permissions(administrator=True)
async def ticketsetup(interaction: discord.Interaction, channel: discord.TextChannel):
    embed = discord.Embed(
        title="🎫 Support - Yume",
        description="Clique sur le bouton ci-dessous pour ouvrir un ticket et contacter le staff !",
        color=discord.Color.blurple()
    )
    await channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message(f"✅ Panel de tickets créé dans {channel.mention} !", ephemeral=True)

@bot.tree.command(name="setticket", description="🎫 Config tickets (rôle + catégorie)")
@app_commands.describe(role="Rôle qui peut gérer les tickets", category="Catégorie des tickets")
@app_commands.checks.has_permissions(administrator=True)
async def setticket(interaction: discord.Interaction, role: discord.Role, category: discord.CategoryChannel = None):
    guild_id = str(interaction.guild.id)
    data["ticket_role"][guild_id] = str(role.id)
    if category:
        data["ticket_category"][guild_id] = str(category.id)
    save_data()
    await interaction.response.send_message(f"✅ Rôle ticket: {role.mention}" + (f"\n📁 Catégorie: {category.name}" if category else ""), ephemeral=True)

# ==================== SLASH: ABSENCE ====================
class AbsenceView(discord.ui.View):
    def __init__(self, requester_id):
        super().__init__(timeout=None)
        self.requester_id = requester_id

    @discord.ui.button(label="Accepter", emoji="✅", style=discord.ButtonStyle.success, custom_id="accept_absence")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        # Vérifier que c'est un staff
        staff_role_id = data["absence_staff"].get(guild_id)
        if staff_role_id:
            staff_role = interaction.guild.get_role(int(staff_role_id))
            if staff_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ Tu n'es pas autorisé à accepter !", ephemeral=True)
                return

        member = interaction.guild.get_member(self.requester_id)
        role_id = data["absence_role"].get(guild_id)
        if role_id and member:
            role = interaction.guild.get_role(int(role_id))
            if role:
                await member.add_roles(role)

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(name="✅ Accepté par", value=interaction.user.mention, inline=False)
        await interaction.response.edit_message(embed=embed, view=None)
        if member:
            try:
                await member.send(f"✅ Ta demande d'absence sur **{interaction.guild.name}** a été acceptée !")
            except:
                pass

    @discord.ui.button(label="Refuser", emoji="❌", style=discord.ButtonStyle.danger, custom_id="refuse_absence")
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        staff_role_id = data["absence_staff"].get(guild_id)
        if staff_role_id:
            staff_role = interaction.guild.get_role(int(staff_role_id))
            if staff_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ Tu n'es pas autorisé à refuser !", ephemeral=True)
                return

        member = interaction.guild.get_member(self.requester_id)
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name="❌ Refusé par", value=interaction.user.mention, inline=False)
        await interaction.response.edit_message(embed=embed, view=None)
        if member:
            try:
                await member.send(f"❌ Ta demande d'absence sur **{interaction.guild.name}** a été refusée.")
            except:
                pass

@bot.tree.command(name="absence", description="🌙 Faire une demande d'absence")
@app_commands.describe(raison="Raison de l'absence", date_debut="Date de début", date_fin="Date de fin")
async def absence(interaction: discord.Interaction, raison: str, date_debut: str, date_fin: str):
    guild_id = str(interaction.guild.id)
    channel_id = data["absence_channel"].get(guild_id)
    if not channel_id:
        await interaction.response.send_message("❌ Le système d'absence n'est pas configuré !", ephemeral=True)
        return

    channel = interaction.guild.get_channel(int(channel_id))
    if not channel:
        await interaction.response.send_message("❌ Salon d'absence introuvable !", ephemeral=True)
        return

    embed = discord.Embed(title="🌙 Demande d'absence", color=discord.Color.orange(), timestamp=datetime.now())
    embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
    embed.add_field(name="👤 Membre", value=interaction.user.mention, inline=False)
    embed.add_field(name="📝 Raison", value=raison, inline=False)
    embed.add_field(name="📅 Du", value=date_debut, inline=True)
    embed.add_field(name="📅 Au", value=date_fin, inline=True)

    await channel.send(embed=embed, view=AbsenceView(interaction.user.id))
    await interaction.response.send_message("✅ Ta demande d'absence a été envoyée au staff !", ephemeral=True)

@bot.tree.command(name="setabsence", description="🌙 Config absence")
@app_commands.describe(role_donne="Rôle donné quand accepté", salon="Salon des demandes", role_staff="Rôle staff qui valide")
@app_commands.checks.has_permissions(administrator=True)
async def setabsence(interaction: discord.Interaction, role_donne: discord.Role, salon: discord.TextChannel, role_staff: discord.Role):
    guild_id = str(interaction.guild.id)
    data["absence_role"][guild_id] = str(role_donne.id)
    data["absence_channel"][guild_id] = str(salon.id)
    data["absence_staff"][guild_id] = str(role_staff.id)
    save_data()
    await interaction.response.send_message(f"✅ Absence configurée !\nRôle: {role_donne.mention}\nSalon: {salon.mention}\nStaff: {role_staff.mention}", ephemeral=True)

# ==================== SLASH: GIVEAWAY ====================
class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.participants = set()

    @discord.ui.button(label="Participer", emoji="🎉", style=discord.ButtonStyle.primary, custom_id="join_giveaway")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.participants.add(interaction.user.id)
        await interaction.response.send_message(f"✅ Tu participes au giveaway ! ({len(self.participants)} participants)", ephemeral=True)

@bot.tree.command(name="giveaway", description="🎉 Lancer un giveaway")
@app_commands.describe(prix="Le prix à gagner", duree="Durée en minutes", gagnants="Nombre de gagnants")
@app_commands.checks.has_permissions(administrator=True)
async def giveaway(interaction: discord.Interaction, prix: str, duree: int, gagnants: int = 1):
    embed = discord.Embed(
        title="🎉 GIVEAWAY 🎉",
        description=f"**Prix:** {prix}\n**Gagnants:** {gagnants}\n**Fin dans:** {duree} minutes\n\nClique sur 🎉 pour participer !",
        color=discord.Color.gold()
    )
    view = GiveawayView()
    await interaction.response.send_message(embed=embed, view=view)
    msg = await interaction.original_response()

    await asyncio.sleep(duree * 60)

    if not view.participants:
        await msg.reply("❌ Personne n'a participé au giveaway !")
        return

    winners = random.sample(list(view.participants), min(gagnants, len(view.participants)))
    winner_mentions = ", ".join([f"<@{w}>" for w in winners])

    result = discord.Embed(
        title="🎉 Giveaway terminé !",
        description=f"**Prix:** {prix}\n**Gagnant(s):** {winner_mentions}",
        color=discord.Color.green()
    )
    await msg.reply(embed=result)

# ==================== SLASH: REACTION ROLES ====================
class ReactionRoleView(discord.ui.View):
    def __init__(self, role_id, label, emoji):
        super().__init__(timeout=None)
        self.role_id = role_id
        button = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary, custom_id=f"rr_{role_id}")
        button.callback = self.button_callback
        self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("❌ Rôle introuvable !", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"➖ Rôle {role.mention} retiré !", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"➕ Rôle {role.mention} ajouté !", ephemeral=True)

@bot.tree.command(name="reactionrole", description="🎭 Créer un message à réaction-rôle")
@app_commands.describe(role="Rôle à donner", titre="Titre du message", description="Description", emoji="Emoji du bouton", label="Texte du bouton")
@app_commands.checks.has_permissions(administrator=True)
async def reactionrole(interaction: discord.Interaction, role: discord.Role, titre: str, description: str, emoji: str = "🎭", label: str = "Récupérer le rôle"):
    embed = discord.Embed(title=titre, description=description, color=discord.Color.blurple())
    await interaction.channel.send(embed=embed, view=ReactionRoleView(role.id, label, emoji))
    await interaction.response.send_message("✅ Message à réaction-rôle créé !", ephemeral=True)

# ==================== SLASH: CONFIG ====================
@bot.tree.command(name="setperm", description="🔐 Définir quels rôles peuvent utiliser une commande")
@app_commands.describe(commande="Nom de la commande (ex: clear)", role1="Rôle 1", role2="Rôle 2 (optionnel)", role3="Rôle 3 (optionnel)")
@app_commands.checks.has_permissions(administrator=True)
async def setperm(interaction: discord.Interaction, commande: str, role1: discord.Role, role2: discord.Role = None, role3: discord.Role = None):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["perms"]:
        data["perms"][guild_id] = {}
    roles = [str(role1.id)]
    if role2:
        roles.append(str(role2.id))
    if role3:
        roles.append(str(role3.id))
    data["perms"][guild_id][commande] = roles
    save_data()
    role_mentions = ", ".join([f"<@&{r}>" for r in roles])
    await interaction.response.send_message(f"✅ La commande `{commande}` peut être utilisée par: {role_mentions}", ephemeral=True)

@bot.tree.command(name="removeperm", description="🔐 Retirer les permissions d'une commande")
@app_commands.describe(commande="Nom de la commande")
@app_commands.checks.has_permissions(administrator=True)
async def removeperm(interaction: discord.Interaction, commande: str):
    guild_id = str(interaction.guild.id)
    if guild_id in data["perms"] and commande in data["perms"][guild_id]:
        del data["perms"][guild_id][commande]
        save_data()
        await interaction.response.send_message(f"✅ Permissions de `{commande}` retirées (admin only).", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Aucune permission configurée pour `{commande}`.", ephemeral=True)

@bot.tree.command(name="permlist", description="🔐 Voir toutes les permissions configurées")
@app_commands.checks.has_permissions(administrator=True)
async def permlist(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id not in data["perms"] or not data["perms"][guild_id]:
        await interaction.response.send_message("❌ Aucune permission configurée.", ephemeral=True)
        return
    embed = discord.Embed(title="🔐 Permissions configurées", color=discord.Color.blue())
    for cmd, roles in data["perms"][guild_id].items():
        role_mentions = ", ".join([f"<@&{r}>" for r in roles])
        embed.add_field(name=f"`{cmd}`", value=role_mentions, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="setcasino", description="🎰 Définir le rôle d'accès au casino")
@app_commands.describe(role="Rôle requis pour le casino")
@app_commands.checks.has_permissions(administrator=True)
async def setcasino(interaction: discord.Interaction, role: discord.Role):
    data["casino_role"][str(interaction.guild.id)] = str(role.id)
    save_data()
    await interaction.response.send_message(f"✅ Rôle casino: {role.mention}", ephemeral=True)

@bot.tree.command(name="setautorole", description="🎭 Définir le rôle automatique à l'arrivée")
@app_commands.describe(role="Rôle donné automatiquement")
@app_commands.checks.has_permissions(administrator=True)
async def setautorole(interaction: discord.Interaction, role: discord.Role):
    data["autorole"][str(interaction.guild.id)] = str(role.id)
    save_data()
    await interaction.response.send_message(f"✅ Auto-rôle: {role.mention}", ephemeral=True)

@bot.tree.command(name="setlaisserole", description="🦮 Définir le rôle qui peut utiliser la laisse")
@app_commands.describe(role="Rôle autorisé")
@app_commands.checks.has_permissions(administrator=True)
async def setlaisserole(interaction: discord.Interaction, role: discord.Role):
    data["laisse_role"][str(interaction.guild.id)] = str(role.id)
    save_data()
    await interaction.response.send_message(f"✅ Rôle laisse: {role.mention}", ephemeral=True)

@bot.tree.command(name="removelaisserole", description="🦮 Retirer le rôle laisse")
@app_commands.checks.has_permissions(administrator=True)
async def removelaisserole(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id in data["laisse_role"]:
        del data["laisse_role"][guild_id]
        save_data()
    await interaction.response.send_message("✅ Rôle laisse retiré.", ephemeral=True)

@bot.tree.command(name="setcounters", description="📊 Créer les salons compteurs")
@app_commands.checks.has_permissions(administrator=True)
async def setcounters(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild

    category = await guild.create_category("📊 Statistiques")
    members_ch = await guild.create_voice_channel(f"👥 Membres: {guild.member_count}", category=category)
    voice_ch = await guild.create_voice_channel("🎙️ En vocal: 0", category=category)
    online_ch = await guild.create_voice_channel("🟢 En ligne: 0", category=category)

    data["counters"][str(guild.id)] = {
        "members": str(members_ch.id),
        "voice": str(voice_ch.id),
        "online": str(online_ch.id)
    }
    save_data()
    await interaction.followup.send("✅ Salons compteurs créés ! (mise à jour toutes les 5 min)", ephemeral=True)

# ==================== ERREURS ====================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant ! Vérifie `&help`")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Membre introuvable !")
    elif isinstance(error, commands.CheckFailure):
        pass  # Déjà géré par perm_check
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