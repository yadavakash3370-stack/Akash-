import os
import asyncio
import re
from datetime import datetime
from flask import Flask
from threading import Thread
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import ChannelInvalid, ChannelPrivate, UsernameNotOccupied, UserNotParticipant
from pymongo import MongoClient

# === Configuration ===
# Yeh data Render ke Environment Variables se automatic utha lega
API_ID = int(os.environ.get("API_ID", 39899558))  
API_HASH = os.environ.get("API_HASH", "a412e0e1b2700bd8ede647a6ccb3177e")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8997774923:AAGieuQneezw1UTgiKhYp2uRhwlE1RD4Xr4")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://yadavakash3370_db_user:yjgpfGX9Zuqxv2&cluster0.jsdjgtz.mongodb.net/?appName=Cluster0")

# Aapka official channel username (Bina @ ke)
AUTH_CHANNEL = "MOTIVATINALTHOUGHTS" 

# === Database Setup ===
mongo = MongoClient(MONGO_URL)
db = mongo["channel_guardian_db"]
users_col = db["users"]
channels_col = db["channels"]

# === Pyrogram Bot Client ===
bot = Client("monitor_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# === Force Join Checker ===
async def is_user_joined(client, message):
    if not AUTH_CHANNEL:
        return True
    try:
        await client.get_chat_member(AUTH_CHANNEL, message.from_user.id)
        return True
    except UserNotParticipant:
        # Yeh button ab sirf aur sirf aapke channel par le jayega
        btn = [[InlineKeyboardButton("📢 Join Our Channel", url=f"https://t.me/{AUTH_CHANNEL}")]]
        await message.reply(
            f"🚀 **To use this bot, you must join our official channel first!**\n\n"
            f"Niche diye gaye button par click karke join karein, aur phir se message bhejein.",
            reply_markup=InlineKeyboardMarkup(btn)
        )
        return False
    except Exception as e:
        print(f"Force Join Check Error: {e}")
        return True

@bot.on_message(filters.command("start"), group=-1)
async def start_handler(client, message):
    message.stop_propagation()
    if not await is_user_joined(client, message):
        return
        
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"name": user_name, "joined": datetime.now()}},
        upsert=True
    )
    welcome = f"""👋 **Welcome {user_name}!**

🛡️ **Channel Guardian Bot**
Main aapke channels ko monitor karne ke liye ready hu!

**Commands:**
/add @channel - Channel add karo
/list - Apne channels dekho
/remove @channel - Channel hatao
/help - Help"""
    await message.reply(welcome)

@bot.on_message(filters.command("add") | filters.command("list") | filters.command("remove") | filters.command("help"), group=-1)
async def all_commands_handler(client, message):
    message.stop_propagation()
    if not await is_user_joined(client, message):
        return
    await message.reply("✅ Command received! Bot is working perfectly under your channel protection.")

# === Flask Web Server (For Render) ===
web = Flask('')

@web.route('/')
def home():
    return "Channel Guardian Bot is alive and secure! 🛡️"

def run_web():
    port = int(os.environ.get('PORT', 10000))
    web.run(host='0.0.0.0', port=port)

# === Main Async Runner ===
async def main():
    print("⚡ Starting Bot Client...")
    await bot.start()
    print("✅ Bot Client started successfully! Channel Guardian is LIVE!")
    await idle()

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
  
