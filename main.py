import os
import asyncio
from datetime import datetime
from flask import Flask
from threading import Thread
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import (
    ChannelInvalid, ChannelPrivate, UsernameNotOccupied,
    UserNotParticipant, FloodWait, ChatAdminRequired
)
from pymongo import MongoClient

# ============================================================
# === CONFIGURATION ===
# ============================================================
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URL = os.environ.get("MONGO_URL", "")
AUTH_CHANNEL = os.environ.get("AUTH_CHANNEL", "MOTIVATINALTHOUGHTS")

FREE_LIMIT = 3
PREMIUM_LIMIT = 1000
MONITOR_INTERVAL = 3600  # 1 hour in seconds

# ============================================================
# === DATABASE SETUP ===
# ============================================================
mongo = MongoClient(MONGO_URL)
db = mongo["channel_guardian_db"]
users_col = db["users"]
channels_col = db["channels"]
messages_col = db["saved_messages"]

# ============================================================
# === BOT CLIENT ===
# ============================================================
bot = Client(
    "monitor_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# ============================================================
# === HELPER FUNCTIONS ===
# ============================================================

def is_premium(user_id):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        return False
    premium_until = user.get("premium_until")
    if not premium_until:
        return False
    return premium_until > datetime.now()

def get_channel_limit(user_id):
    return PREMIUM_LIMIT if is_premium(user_id) else FREE_LIMIT

def get_user_channels(user_id):
    return list(channels_col.find({"user_id": user_id}))

async def is_user_joined(client, message):
    if not AUTH_CHANNEL:
        return True
    try:
        await client.get_chat_member(AUTH_CHANNEL, message.from_user.id)
        return True
    except UserNotParticipant:
        btn = [[InlineKeyboardButton("📢 Join Our Channel", url=f"https://t.me/{AUTH_CHANNEL}")]]
        await message.reply(
            "🚫 **Pehle hamara channel join karo!**\n\nJoin karne ke baad dobara try karo.",
            reply_markup=InlineKeyboardMarkup(btn)
        )
        return False
    except Exception:
        return True

async def check_channel_status(client, username):
    """Channel ki current status check karo"""
    try:
        chat = await client.get_chat(username)
        return {
            "status": "active",
            "title": chat.title,
            "members": getattr(chat, "members_count", 0),
            "username": getattr(chat, "username", None),
            "invite_link": getattr(chat, "invite_link", None),
        }
    except (ChannelInvalid, ChannelPrivate):
        return {"status": "banned", "title": None}
    except UsernameNotOccupied:
        return {"status": "deleted", "title": None}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ============================================================
# === COMMANDS ===
# ============================================================

@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    if not await is_user_joined(client, message):
        return

    user_id = message.from_user.id
    user_name = message.from_user.first_name
    premium = is_premium(user_id)

    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"name": user_name, "last_seen": datetime.now()},
         "$setOnInsert": {"joined": datetime.now()}},
        upsert=True
    )

    badge = "💎 Premium" if premium else "🆓 Free"
    limit = get_channel_limit(user_id)
    current = len(get_user_channels(user_id))

    welcome = f"""👋 **Welcome {user_name}!**

🛡️ **Channel Guardian Bot**
Aapke channels ko 24/7 monitor karta hoon!

**📊 Your Status:** {badge}
**📡 Channels:** {current}/{limit}

**🆓 Free Commands:**
/add @username — Channel add karo
/list — Apne channels dekho  
/remove @username — Channel hatao
/status @username — Channel check karo
/keywords — Alert keywords set karo

**💎 Premium (₹99/month):**
/premium — Features dekhो aur upgrade karo

**ℹ️ Info:**
/help — Complete help"""

    btn = [[InlineKeyboardButton("💎 Get Premium", callback_data="premium_info"),
            InlineKeyboardButton("📢 Our Channel", url=f"https://t.me/{AUTH_CHANNEL}")]]
    await message.reply(welcome, reply_markup=InlineKeyboardMarkup(btn))


@bot.on_message(filters.command("add"))
async def add_channel(client, message):
    if not await is_user_joined(client, message):
        return

    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2:
        await message.reply(
            "❌ **Usage:** `/add @username`\n\n"
            "Example: `/add @mychannel`"
        )
        return

    username = args[1].replace("@", "").strip()
    limit = get_channel_limit(user_id)
    current_channels = get_user_channels(user_id)

    if len(current_channels) >= limit:
        premium = is_premium(user_id)
        if not premium:
            btn = [[InlineKeyboardButton("💎 Get Premium", callback_data="premium_info")]]
            await message.reply(
                f"❌ **Free limit reached! ({FREE_LIMIT}/{FREE_LIMIT})**\n\n"
                "💎 Premium lo aur **1000+ channels** monitor karo sirf ₹99/month mein!",
                reply_markup=InlineKeyboardMarkup(btn)
            )
        else:
            await message.reply(f"❌ Maximum limit reach ho gayi ({PREMIUM_LIMIT}).")
        return

    # Already added check
    existing = channels_col.find_one({"user_id": user_id, "username": username.lower()})
    if existing:
        await message.reply(f"⚠️ `@{username}` already added hai!")
        return

    # Channel check karo
    msg = await message.reply(f"🔍 `@{username}` check kar raha hoon...")
    status = await check_channel_status(client, username)

    if status["status"] == "active":
        channels_col.insert_one({
            "user_id": user_id,
            "username": username.lower(),
            "title": status["title"],
            "added_on": datetime.now(),
            "last_checked": datetime.now(),
            "last_status": "active",
            "invite_link": status.get("invite_link"),
            "keywords": []
        })
        await msg.edit(
            f"✅ **Channel Added!**\n\n"
            f"📛 **Name:** {status['title']}\n"
            f"🔗 **Username:** @{username}\n"
            f"👥 **Members:** {status.get('members', 'N/A')}\n\n"
            f"🛡️ Ab main isko monitor karta rahunga!"
        )
    elif status["status"] == "banned":
        await msg.edit(f"❌ `@{username}` already banned/private hai. Add nahi kar sakta.")
    elif status["status"] == "deleted":
        await msg.edit(f"❌ `@{username}` exist nahi karta.")
    else:
        await msg.edit(f"❌ Error: {status.get('error', 'Unknown error')}")


@bot.on_message(filters.command("list"))
async def list_channels(client, message):
    if not await is_user_joined(client, message):
        return

    user_id = message.from_user.id
    channels = get_user_channels(user_id)

    if not channels:
        await message.reply(
            "📭 **Koi channel add nahi kiya abhi tak.**\n\n"
            "Use `/add @username` to add a channel!"
        )
        return

    limit = get_channel_limit(user_id)
    text = f"📋 **Aapke Monitored Channels ({len(channels)}/{limit}):**\n\n"

    for i, ch in enumerate(channels, 1):
        status_emoji = "✅" if ch.get("last_status") == "active" else "❌"
        text += f"{i}. {status_emoji} **{ch.get('title', ch['username'])}**\n"
        text += f"   🔗 @{ch['username']}\n"
        text += f"   📅 Added: {ch['added_on'].strftime('%d %b %Y')}\n\n"

    await message.reply(text)


@bot.on_message(filters.command("remove"))
async def remove_channel(client, message):
    if not await is_user_joined(client, message):
        return

    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2:
        await message.reply("❌ **Usage:** `/remove @username`")
        return

    username = args[1].replace("@", "").strip().lower()
    result = channels_col.delete_one({"user_id": user_id, "username": username})

    if result.deleted_count > 0:
        await message.reply(f"✅ `@{username}` monitor list se hata diya!")
    else:
        await message.reply(f"❌ `@{username}` aapki list mein nahi tha.")


@bot.on_message(filters.command("status"))
async def channel_status(client, message):
    if not await is_user_joined(client, message):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ **Usage:** `/status @username`")
        return

    username = args[1].replace("@", "").strip()
    msg = await message.reply(f"🔍 Checking `@{username}`...")
    status = await check_channel_status(client, username)

    if status["status"] == "active":
        await msg.edit(
            f"✅ **Channel Active Hai!**\n\n"
            f"📛 **Name:** {status['title']}\n"
            f"🔗 **Username:** @{username}\n"
            f"👥 **Members:** {status.get('members', 'N/A')}"
        )
    elif status["status"] == "banned":
        await msg.edit(f"❌ **`@{username}` BAN HO GAYA HAI!**\n\nChannel access nahi hai.")
    elif status["status"] == "deleted":
        await msg.edit(f"🗑️ **`@{username}` delete ho gaya hai.**")
    else:
        await msg.edit(f"⚠️ **Error:** {status.get('error')}")


@bot.on_message(filters.command("keywords"))
async def set_keywords(client, message):
    if not await is_user_joined(client, message):
        return

    user_id = message.from_user.id
    args = message.text.split(None, 2)

    if len(args) < 3:
        await message.reply(
            "🔑 **Keywords set karo:**\n\n"
            "**Usage:** `/keywords @channel word1, word2, word3`\n\n"
            "**Example:** `/keywords @mychannel new link, backup, moved to`\n\n"
            "Jab bhi in words wala message aaye, main tumhe alert karunga!"
        )
        return

    username = args[1].replace("@", "").strip().lower()
    keywords = [k.strip().lower() for k in args[2].split(",")]

    result = channels_col.update_one(
        {"user_id": user_id, "username": username},
        {"$set": {"keywords": keywords}}
    )

    if result.matched_count > 0:
        kw_list = "\n".join([f"• {k}" for k in keywords])
        await message.reply(f"✅ **Keywords set ho gaye `@{username}` ke liye:**\n\n{kw_list}")
    else:
        await message.reply(f"❌ `@{username}` aapki list mein nahi hai. Pehle `/add @{username}` karo.")


@bot.on_message(filters.command("premium"))
async def premium_info(client, message):
    if not await is_user_joined(client, message):
        return

    user_id = message.from_user.id
    premium = is_premium(user_id)

    if premium:
        user = users_col.find_one({"user_id": user_id})
        until = user["premium_until"].strftime("%d %b %Y")
        await message.reply(f"💎 **Aap already Premium Member hain!**\n\n📅 Valid till: **{until}**")
        return

    text = """💎 **PREMIUM PLAN — ₹99/month**

🆓 **Free vs 💎 Premium:**

| Feature | Free | Premium |
|---------|------|---------|
| Channels | 3 | 1000+ |
| Check Speed | 1hr | Real-time |
| Keywords | ✅ | ✅ |
| Auto-Join | ❌ | ✅ |
| Msg Backup | ❌ | ✅ (100 msgs) |
| Priority Support | ❌ | ✅ |

💳 **Payment ke liye admin se contact karo:**
@YourAdminUsername

/start — Back to menu"""

    btn = [[InlineKeyboardButton("💳 Buy Premium", url="https://t.me/YourAdminUsername")]]
    await message.reply(text, reply_markup=InlineKeyboardMarkup(btn))


@bot.on_message(filters.command("help"))
async def help_handler(client, message):
    if not await is_user_joined(client, message):
        return

    await message.reply(
        "📖 **COMPLETE HELP**\n\n"
        "**Basic Commands:**\n"
        "/start — Bot start karo\n"
        "/add @ch — Channel add karo\n"
        "/list — Channels dekho\n"
        "/remove @ch — Channel hatao\n"
        "/status @ch — Channel check karo\n"
        "/keywords @ch word1, word2 — Alert keywords\n"
        "/premium — Premium info\n\n"
        "**How it works:**\n"
        "1️⃣ /add @channel karo\n"
        "2️⃣ Bot har ghante check karega\n"
        "3️⃣ Ban hone par turant alert aayega\n"
        "4️⃣ New link mile to forward ho jayega\n\n"
        "**Problems?** @YourAdminUsername se contact karo"
    )


# ============================================================
# === CALLBACK HANDLERS ===
# ============================================================

@bot.on_callback_query(filters.regex("premium_info"))
async def premium_callback(client, callback_query):
    await callback_query.answer()
    await callback_query.message.reply(
        "💎 **Premium Plan — ₹99/month**\n\n"
        "✅ 1000+ Channels\n"
        "✅ Real-time alerts\n"
        "✅ Auto-join new channels\n"
        "✅ Message backup\n\n"
        "Contact: @YourAdminUsername"
    )


# ============================================================
# === BACKGROUND MONITOR ===
# ============================================================

async def monitor_channels():
    """Background task — sabhi channels check karta rahega"""
    await asyncio.sleep(60)  # Bot start hone ke 1 min baad shuru ho
    
    while True:
        try:
            print("🔄 Channel monitoring cycle starting...")
            all_channels = list(channels_col.find({"last_status": "active"}))
            
            for channel in all_channels:
                try:
                    username = channel["username"]
                    user_id = channel["user_id"]
                    old_status = channel.get("last_status", "active")

                    status = await check_channel_status(bot, username)
                    new_status = status["status"]

                    # Status change hua?
                    if new_status != old_status:
                        channels_col.update_one(
                            {"_id": channel["_id"]},
                            {"$set": {"last_status": new_status, "last_checked": datetime.now()}}
                        )

                        if new_status == "banned":
                            await bot.send_message(
                                user_id,
                                f"🚨 **ALERT! Channel BAN HO GAYA!**\n\n"
                                f"📛 **Channel:** {channel.get('title', username)}\n"
                                f"🔗 **Username:** @{username}\n"
                                f"⏰ **Time:** {datetime.now().strftime('%d %b %Y, %I:%M %p')}\n\n"
                                f"😔 Is channel ka content ab accessible nahi hai.\n"
                                f"💎 Premium lo — **backup feature** se purane messages save karo!"
                            )
                        elif new_status == "deleted":
                            await bot.send_message(
                                user_id,
                                f"⚠️ **Channel Delete Ho Gaya!**\n\n"
                                f"🔗 @{username} ab exist nahi karta.\n"
                                f"Monitoring list se hata diya gaya."
                            )
                            channels_col.delete_one({"_id": channel["_id"]})

                    else:
                        # Status same hai, sirf last_checked update karo
                        channels_col.update_one(
                            {"_id": channel["_id"]},
                            {"$set": {"last_checked": datetime.now()}}
                        )

                    await asyncio.sleep(2)  # Rate limit avoid karne ke liye

                except FloodWait as e:
                    print(f"FloodWait: sleeping {e.value}s")
                    await asyncio.sleep(e.value)
                except Exception as e:
                    print(f"Monitor error for {channel.get('username')}: {e}")

            print(f"✅ Monitor cycle done. Next in {MONITOR_INTERVAL//60} minutes.")
            await asyncio.sleep(MONITOR_INTERVAL)

        except Exception as e:
            print(f"❌ Monitor loop error: {e}")
            await asyncio.sleep(60)


# ============================================================
# === MESSAGE LISTENER (Keywords) ===
# ============================================================

@bot.on_message(filters.channel)
async def channel_message_listener(client, message):
    """Channel messages sun — keywords match karo"""
    try:
        chat = message.chat
        username = getattr(chat, "username", None)
        if not username:
            return

        username = username.lower()
        text = message.text or message.caption or ""
        if not text:
            return

        # Is channel ke saare users find karo jinhone keywords set kiye hain
        watchers = list(channels_col.find({
            "username": username,
            "keywords": {"$exists": True, "$ne": []}
        }))

        for watcher in watchers:
            keywords = watcher.get("keywords", [])
            matched = [kw for kw in keywords if kw in text.lower()]

            if matched:
                user_id = watcher["user_id"]
                kw_text = ", ".join([f"`{k}`" for k in matched])
                await bot.send_message(
                    user_id,
                    f"🔔 **Keyword Alert!**\n\n"
                    f"📢 **Channel:** @{username}\n"
                    f"🔑 **Matched Keywords:** {kw_text}\n\n"
                    f"📝 **Message:**\n{text[:300]}{'...' if len(text) > 300 else ''}"
                )

    except Exception as e:
        print(f"Channel listener error: {e}")


# ============================================================
# === FLASK WEB SERVER ===
# ============================================================

web = Flask('')

@web.route('/')
def home():
    total_users = users_col.count_documents({})
    total_channels = channels_col.count_documents({})
    return f"""
    <h1>🛡️ Channel Guardian Bot</h1>
    <p>Status: <b>LIVE ✅</b></p>
    <p>Total Users: <b>{total_users}</b></p>
    <p>Monitored Channels: <b>{total_channels}</b></p>
    """

def run_web():
    port = int(os.environ.get('PORT', 10000))
    web.run(host='0.0.0.0', port=port)


# ============================================================
# === MAIN ===
# ============================================================

async def main():
    print("⚡ Starting Bot...")
    await bot.start()
    me = await bot.get_me()
    print(f"✅ Bot started: @{me.username}")
    
    # Background monitor start karo
    asyncio.create_task(monitor_channels())
    print("🔄 Background monitor started!")
    
    await idle()

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
          
