# ============================================================
# CHANNEL GUARDIAN BOT — Complete Professional Version
# ============================================================

import os
import asyncio
import logging
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery
)
from pyrogram.errors import (
    ChannelInvalid, ChannelPrivate, UsernameNotOccupied,
    UserNotParticipant, FloodWait, ChatAdminRequired,
    PeerIdInvalid
)
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# ============================================================
# LOGGING SETUP
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================
API_ID        = int(os.environ.get("API_ID", "39899558"))
API_HASH      = os.environ.get("API_HASH", "a412e0e1b2700bd8ede647a6ccb3177e")
BOT_TOKEN     = os.environ.get("BOT_TOKEN", "8683394154:AAHBZB9TaNmxjAl5EQ03WoZ1UgnRgBaQEy8")
MONGO_URL     = os.environ.get("MONGO_URL", "mongodb+srv://yadavakash3370_db_user:yjggfGX9ZeuqxV2G@cluster0.jsdjgtr.mongodb.net/?appName=Cluster0")
AUTH_CHANNEL  = os.environ.get("AUTH_CHANNEL", "MOTIVATINALTHOUGHTS")
ADMIN_IDS     = [int(x) for x in os.environ.get("ADMIN_IDS", "8675781167").split(",") if x.strip().isdigit()]
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Akash_50")

FREE_LIMIT        = 3
PREMIUM_LIMIT     = 1000
MONITOR_INTERVAL  = 3600      # 1 hour
BACKUP_MSG_LIMIT  = 100       # Premium: last 100 messages save

# ============================================================
# DATABASE
# ============================================================
try:
    mongo = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    mongo.server_info()
    db = mongo["channel_guardian_db"]
    log.info("✅ MongoDB connected!")
except ConnectionFailure:
    log.error("❌ MongoDB connection failed!")
    db = None

users_col    = db["users"]    if db is not None else None
channels_col = db["channels"] if db is not None else None
messages_col = db["messages"] if db is not None else None
payments_col = db["payments"] if db is not None else None

# ============================================================
# BOT CLIENT
# ============================================================
bot = Client(
    "channel_guardian",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# ============================================================
# DATABASE HELPERS
# ============================================================

def get_user(user_id: int):
    return users_col.find_one({"user_id": user_id})

def upsert_user(user_id: int, data: dict):
    users_col.update_one(
        {"user_id": user_id},
        {"$set": data, "$setOnInsert": {"joined": datetime.now(), "user_id": user_id}},
        upsert=True
    )

def is_premium(user_id: int) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    until = user.get("premium_until")
    return bool(until and until > datetime.now())

def get_limit(user_id: int) -> int:
    return PREMIUM_LIMIT if is_premium(user_id) else FREE_LIMIT

def get_channels(user_id: int) -> list:
    return list(channels_col.find({"user_id": user_id}))

def get_channel(user_id: int, username: str):
    return channels_col.find_one({"user_id": user_id, "username": username.lower()})

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ============================================================
# FORCE JOIN CHECKER
# ============================================================

async def check_joined(client: Client, message: Message) -> bool:
    if not AUTH_CHANNEL:
        return True
    try:
        await client.get_chat_member(AUTH_CHANNEL, message.from_user.id)
        return True
    except UserNotParticipant:
        btn = [[InlineKeyboardButton(
            "📢 Join Channel", url=f"https://t.me/{AUTH_CHANNEL}"
        )]]
        await message.reply(
            "🔒 **Pehle hamare channel ko join karo!**\n\n"
            "Join karne ke baad dobara command use karo.",
            reply_markup=InlineKeyboardMarkup(btn)
        )
        return False
    except Exception:
        return True

# ============================================================
# CHANNEL STATUS CHECKER
# ============================================================

async def fetch_channel_info(client: Client, username: str) -> dict:
    try:
        chat = await client.get_chat(username)
        return {
            "alive": True,
            "title": chat.title,
            "members": getattr(chat, "members_count", 0),
            "username": getattr(chat, "username", None),
            "invite_link": getattr(chat, "invite_link", None),
            "description": getattr(chat, "description", ""),
        }
    except (ChannelInvalid, ChannelPrivate, ChatAdminRequired):
        return {"alive": False, "reason": "banned"}
    except (UsernameNotOccupied, PeerIdInvalid):
        return {"alive": False, "reason": "deleted"}
    except Exception as e:
        return {"alive": False, "reason": "error", "detail": str(e)}

# ============================================================
# MESSAGE TEMPLATES
# ============================================================

def home_text(name: str, user_id: int) -> str:
    premium = is_premium(user_id)
    badge   = "💎 Premium" if premium else "🆓 Free"
    limit   = get_limit(user_id)
    count   = len(get_channels(user_id))

    if premium:
        user = get_user(user_id)
        until = user["premium_until"].strftime("%d %b %Y")
        badge += f" (till {until})"

    return (
        f"👋 **Welcome, {name}!**\n\n"
        f"🛡️ **Channel Guardian Bot**\n"
        f"Aapke channels ko 24/7 silently monitor karta hoon.\n"
        f"Ban hone par **turant alert** bhejta hoon.\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"**📊 Aapka Plan:** {badge}\n"
        f"**📡 Channels:** {count}/{limit}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"Niche se koi bhi option choose karo 👇"
    )

def home_buttons(user_id: int) -> InlineKeyboardMarkup:
    premium = is_premium(user_id)
    rows = [
        [
            InlineKeyboardButton("📋 My Channels", callback_data="my_channels"),
            InlineKeyboardButton("➕ Add Channel", callback_data="how_to_add"),
        ],
        [
            InlineKeyboardButton("💎 Premium" if not premium else "💎 My Plan", callback_data="premium_menu"),
            InlineKeyboardButton("📖 Help", callback_data="help_menu"),
        ],
        [
            InlineKeyboardButton("📢 Official Channel", url=f"https://t.me/{AUTH_CHANNEL}"),
        ]
    ]
    return InlineKeyboardMarkup(rows)

# ============================================================
# /start
# ============================================================

@bot.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    if not await check_joined(client, message):
        return

    user_id   = message.from_user.id
    user_name = message.from_user.first_name

    upsert_user(user_id, {
        "name": user_name,
        "username": message.from_user.username,
        "last_seen": datetime.now(),
    })

    await message.reply(
        home_text(user_name, user_id),
        reply_markup=home_buttons(user_id)
    )

# ============================================================
# /add
# ============================================================

@bot.on_message(filters.command("add"))
async def add_cmd(client: Client, message: Message):
    if not await check_joined(client, message):
        return

    user_id = message.from_user.id
    args    = message.text.split()

    if len(args) < 2:
        await message.reply(
            "❌ **Usage:** `/add @username`\n\n"
            "**Example:** `/add @mychannel`\n\n"
            "Channel ka username chahiye (@ ke saath ya bina bhi chalega)."
        )
        return

    username = args[1].replace("@", "").strip().lower()
    limit    = get_limit(user_id)
    channels = get_channels(user_id)

    if len(channels) >= limit:
        if not is_premium(user_id):
            btn = [[InlineKeyboardButton("💎 Premium Lo", callback_data="premium_menu")]]
            await message.reply(
                f"❌ **Free limit full! ({FREE_LIMIT}/{FREE_LIMIT})**\n\n"
                f"💎 **Premium** lo aur **1000+ channels** monitor karo\n"
                f"sirf **₹99/month** mein!",
                reply_markup=InlineKeyboardMarkup(btn)
            )
        else:
            await message.reply(f"❌ Maximum limit ({PREMIUM_LIMIT}) reach ho gayi.")
        return

    if get_channel(user_id, username):
        await message.reply(f"⚠️ `@{username}` pehle se added hai!")
        return

    msg = await message.reply(f"🔍 `@{username}` check kar raha hoon...")
    info = await fetch_channel_info(client, username)

    if info["alive"]:
        channels_col.insert_one({
            "user_id":      user_id,
            "username":     username,
            "title":        info["title"],
            "members":      info["members"],
            "added_on":     datetime.now(),
            "last_checked": datetime.now(),
            "last_status":  "active",
            "invite_link":  info.get("invite_link"),
            "keywords":     [],
            "notify":       True,
        })
        await msg.edit(
            f"✅ **Channel Added!**\n\n"
            f"📛 **Name:** {info['title']}\n"
            f"🔗 **Username:** @{username}\n"
            f"👥 **Members:** {info['members']:,}\n\n"
            f"🛡️ Ab main isko **24/7 monitor** karta rahunga.\n"
            f"Ban hone par **turant alert** bhejunga!"
        )
        log.info(f"User {user_id} added channel @{username}")
    elif info["reason"] == "banned":
        await msg.edit(
            f"❌ `@{username}` **already banned/private** hai.\n"
            f"Iska matlab channel accessible nahi hai."
        )
    elif info["reason"] == "deleted":
        await msg.edit(f"❌ `@{username}` **exist nahi karta.**")
    else:
        await msg.edit(f"⚠️ Error check karte waqt: `{info.get('detail', 'Unknown')}`")

# ============================================================
# /list
# ============================================================

@bot.on_message(filters.command("list"))
async def list_cmd(client: Client, message: Message):
    if not await check_joined(client, message):
        return

    user_id  = message.from_user.id
    channels = get_channels(user_id)

    if not channels:
        await message.reply(
            "📭 **Koi channel add nahi kiya abhi tak.**\n\n"
            "Use `/add @username` to start monitoring!"
        )
        return

    limit = get_limit(user_id)
    text  = f"📋 **Monitored Channels ({len(channels)}/{limit}):**\n\n"

    for i, ch in enumerate(channels, 1):
        emoji  = "✅" if ch.get("last_status") == "active" else "❌"
        title  = ch.get("title", ch["username"])
        added  = ch["added_on"].strftime("%d %b %Y")
        checked = ch.get("last_checked")
        checked_str = checked.strftime("%d %b, %I:%M %p") if checked else "Never"
        kw_count = len(ch.get("keywords", []))

        text += (
            f"{i}. {emoji} **{title}**\n"
            f"   🔗 @{ch['username']}\n"
            f"   📅 Added: {added}\n"
            f"   🕐 Last check: {checked_str}\n"
        )
        if kw_count:
            text += f"   🔑 Keywords: {kw_count} set\n"
        text += "\n"

    await message.reply(text)

# ============================================================
# /remove
# ============================================================

@bot.on_message(filters.command("remove"))
async def remove_cmd(client: Client, message: Message):
    if not await check_joined(client, message):
        return

    user_id = message.from_user.id
    args    = message.text.split()

    if len(args) < 2:
        await message.reply("❌ **Usage:** `/remove @username`")
        return

    username = args[1].replace("@", "").strip().lower()
    result   = channels_col.delete_one({"user_id": user_id, "username": username})

    if result.deleted_count:
        await message.reply(f"✅ `@{username}` monitoring se hata diya gaya!")
    else:
        await message.reply(
            f"❌ `@{username}` aapki list mein nahi tha.\n"
            f"Check karo `/list` se."
        )

# ============================================================
# /status
# ============================================================

@bot.on_message(filters.command("status"))
async def status_cmd(client: Client, message: Message):
    if not await check_joined(client, message):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ **Usage:** `/status @username`")
        return

    username = args[1].replace("@", "").strip()
    msg  = await message.reply(f"🔍 Checking `@{username}`...")
    info = await fetch_channel_info(client, username)

    if info["alive"]:
        await msg.edit(
            f"✅ **Channel Active Hai!**\n\n"
            f"📛 **Name:** {info['title']}\n"
            f"🔗 **Username:** @{username}\n"
            f"👥 **Members:** {info['members']:,}\n"
            f"📝 **Description:** {info['description'][:100] or 'N/A'}"
        )
    elif info["reason"] == "banned":
        await msg.edit(
            f"🚨 **`@{username}` BAN HO GAYA HAI!**\n\n"
            f"Channel ab accessible nahi hai."
        )
    elif info["reason"] == "deleted":
        await msg.edit(f"🗑️ **`@{username}` delete ho gaya hai.**")
    else:
        await msg.edit(f"⚠️ Error: `{info.get('detail')}`")

# ============================================================
# /keywords
# ============================================================

@bot.on_message(filters.command("keywords"))
async def keywords_cmd(client: Client, message: Message):
    if not await check_joined(client, message):
        return

    user_id = message.from_user.id
    parts   = message.text.split(None, 2)

    if len(parts) < 3:
        await message.reply(
            "🔑 **Keyword Alert Setup**\n\n"
            "**Usage:**\n"
            "`/keywords @channel word1, word2, word3`\n\n"
            "**Example:**\n"
            "`/keywords @mychannel new link, backup, moved to, join now`\n\n"
            "Jab bhi in keywords wala message channel mein aaye,\n"
            "main **turant alert** bhejunga! 🔔\n\n"
            "**Keywords clear karne ke liye:**\n"
            "`/keywords @channel clear`"
        )
        return

    username = parts[1].replace("@", "").strip().lower()
    kw_input = parts[2].strip()

    ch = get_channel(user_id, username)
    if not ch:
        await message.reply(
            f"❌ `@{username}` list mein nahi hai.\n"
            f"Pehle `/add @{username}` karo."
        )
        return

    if kw_input.lower() == "clear":
        channels_col.update_one(
            {"user_id": user_id, "username": username},
            {"$set": {"keywords": []}}
        )
        await message.reply(f"✅ `@{username}` ke saare keywords clear ho gaye!")
        return

    keywords = [k.strip().lower() for k in kw_input.split(",") if k.strip()]
    channels_col.update_one(
        {"user_id": user_id, "username": username},
        {"$set": {"keywords": keywords}}
    )

    kw_list = "\n".join([f"  • `{k}`" for k in keywords])
    await message.reply(
        f"✅ **Keywords set ho gaye `@{username}` ke liye:**\n\n"
        f"{kw_list}\n\n"
        f"🔔 In words ka koi bhi message aate hi alert bhejunga!"
    )

# ============================================================
# /premium
# ============================================================

@bot.on_message(filters.command("premium"))
async def premium_cmd(client: Client, message: Message):
    if not await check_joined(client, message):
        return

    user_id = message.from_user.id

    if is_premium(user_id):
        user  = get_user(user_id)
        until = user["premium_until"].strftime("%d %B %Y")
        await message.reply(
            f"💎 **Aap Premium Member Hain!**\n\n"
            f"📅 **Valid Till:** {until}\n\n"
            f"✅ 1000+ channels\n"
            f"✅ Real-time alerts\n"
            f"✅ Message backup\n"
            f"✅ Auto-join new links\n"
            f"✅ Priority support"
        )
        return

    btn = [[InlineKeyboardButton("💳 Buy Premium — ₹99/month", url=f"https://t.me/{ADMIN_USERNAME}")]]
    await message.reply(
        "💎 **PREMIUM PLAN — ₹99/month**\n\n"
        "┌─────────────────────────┐\n"
        "│  🆓 Free   vs  💎 Premium │\n"
        "├─────────────────────────┤\n"
        "│ Channels: 3  →  1000+   │\n"
        "│ Alerts:  1hr →  Instant │\n"
        "│ Backup:  ❌  →  ✅       │\n"
        "│ Auto-join: ❌ →  ✅      │\n"
        "│ Support: ❌  →  ✅       │\n"
        "└─────────────────────────┘\n\n"
        "**Payment Method:** UPI / Bank Transfer\n"
        "**Contact:** @" + ADMIN_USERNAME + "\n\n"
        "Payment karne ke baad admin ko screenshot bhejo —\n"
        "24 ghante mein activate ho jayega!",
        reply_markup=InlineKeyboardMarkup(btn)
    )

# ============================================================
# /help
# ============================================================

@bot.on_message(filters.command("help"))
async def help_cmd(client: Client, message: Message):
    if not await check_joined(client, message):
        return

    await message.reply(
        "📖 **CHANNEL GUARDIAN — COMPLETE GUIDE**\n\n"
        "**Basic Commands:**\n"
        "`/add @channel` — Channel monitor karo\n"
        "`/list` — Sabhi channels dekho\n"
        "`/remove @channel` — Monitoring band karo\n"
        "`/status @channel` — Abhi check karo\n\n"
        "**Alerts Setup:**\n"
        "`/keywords @ch word1, word2` — Keywords set karo\n\n"
        "**Account:**\n"
        "`/premium` — Plan upgrade karo\n"
        "`/me` — Apni info dekho\n\n"
        "**How Bot Works:**\n"
        "1️⃣ `/add @channel` karo\n"
        "2️⃣ Bot har ghante silently check karta hai\n"
        "3️⃣ Ban hone par **turant** alert aata hai\n"
        "4️⃣ Keywords match hone par bhi alert aata hai\n\n"
        "**Issues?**\n"
        f"Contact: @{ADMIN_USERNAME}"
    )

# ============================================================
# /me
# ============================================================

@bot.on_message(filters.command("me"))
async def me_cmd(client: Client, message: Message):
    if not await check_joined(client, message):
        return

    user_id  = message.from_user.id
    user     = get_user(user_id) or {}
    premium  = is_premium(user_id)
    channels = get_channels(user_id)
    limit    = get_limit(user_id)
    joined   = user.get("joined", datetime.now()).strftime("%d %b %Y")

    plan_text = "🆓 Free"
    if premium:
        until = user["premium_until"].strftime("%d %b %Y")
        plan_text = f"💎 Premium (till {until})"

    await message.reply(
        f"👤 **Your Profile**\n\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"👤 **Name:** {message.from_user.first_name}\n"
        f"📅 **Joined:** {joined}\n"
        f"🏷️ **Plan:** {plan_text}\n"
        f"📡 **Channels:** {len(channels)}/{limit}\n"
    )

# ============================================================
# ADMIN COMMANDS
# ============================================================

@bot.on_message(filters.command("addpremium") & filters.user(ADMIN_IDS))
async def add_premium_cmd(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 3:
        await message.reply("**Usage:** `/addpremium USER_ID DAYS`\nExample: `/addpremium 123456789 30`")
        return

    try:
        target_id = i
