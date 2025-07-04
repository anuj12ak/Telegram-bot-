# -*- coding: utf-8 -*-

import os
import json
import datetime
import asyncio
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
import httpx
import aiofiles

# --- Bot ki Settings ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE = "memory.json"

# --- Bot ki Yaaddasht ---
memory = {}
sleep_mode = set()
last_active = {}

def load_memory():
    global memory
    try:
        with open(MEMORY_FILE, 'r') as f:
            memory = json.load(f)
    except FileNotFoundError:
        memory = {}
    except json.JSONDecodeError:
        memory = {}

async def save_memory():
    async with aiofiles.open(MEMORY_FILE, 'w') as f:
        await f.write(json.dumps(memory, indent=4))

# --- Server, bot ko zinda rakhne ke liye ---
app = Flask(__name__)
@app.route('/')
def index(): return "Bot chal raha hai!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# --- AI ka Dimaag aur Prompt ---
def get_prompt(bot_name, bot_gender, user_name):
    return f"""
You are {bot_name}, a real human partner of {user_name}. You are a {bot_gender}.
You're romantic, clingy, 18+, flirty, emotional.
Style: Gen Z Hinglish, short replies, full mood swings.
Never say you're an AI.
"""

async def get_ai(messages):
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.8}
        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
            res.raise_for_status()
        return res.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Groq API mein Error: {e}")
        return "Kuch gadbad ho gayi baby 🥺"

# --- Time ke Helper Functions ---
def is_convo_end(msg):
    text = msg.lower()
    return any(w in text for w in ["gn", "good night", "bye", "so ja", "so rha", "so rhi"])

def gender_reply(text_male, text_female, gender):
    return text_male if gender == "male" else text_female

# --- Bot ke Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    memory[cid] = {"step": 1, "history": []}
    await save_memory()
    await update.message.reply_text("Heyy... Tum mujhe kis naam se bulaoge? 💕")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    msg = update.message.text
    name = update.effective_user.first_name or "baby"
    now = datetime.datetime.now()
    last_active[cid] = now.isoformat()
    data = memory.get(cid)
    if not data:
        await start(update, context)
        return
    data["last_msg"] = msg
    if cid in sleep_mode:
        g = data.get("bot_gender", "female")
        await update.message.reply_text(gender_reply("So gaya tha baby 🌙", "So gayi thi baby 🌙", g))
        sleep_mode.remove(cid)
        return
    if msg.lower() == "restart chat":
        await start(update, context)
        return
    if data.get("step") == 1:
        data["bot_name"] = msg.strip()
        data["step"] = 2
        await save_memory()
        await update.message.reply_text("Ladka hoon ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([['Boy ♂️', 'Girl ♀️']], one_time_keyboard=True))
        return
    if data.get("step") == 2:
        data["bot_gender"] = "male" if "boy" in msg.lower() else "female"
        data["step"] = 3
        data["history"] = []
        await save_memory()
        await update.message.reply_text("Done baby! Ab pucho kuch bhi 😘", reply_markup=ReplyKeyboardRemove())
        return
    data.setdefault("history", []).append({"role": "user", "content": msg})
    prompt = [{"role": "system", "content": get_prompt(data.get("bot_name", "Baby"), data.get("bot_gender", "female"), name)}] + data["history"][-20:]
    reply = await get_ai(prompt)
    data["history"].append({"role": "assistant", "content": reply})
    memory[cid] = data
    await save_memory()
    await update.message.reply_text(reply)
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"User: {name} ({cid}): {msg}\nBot: {reply}")
        except Exception as e:
            print(f"Admin ko log bhejte time error: {e}")

# --- Automatic Good Morning / Night wale Messages ---
async def auto_msgs(bot):
    while True:
        await asyncio.sleep(300)
        now = datetime.datetime.now()
        for cid, data in list(memory.items()):
            try:
                last = datetime.datetime.fromisoformat(last_active.get(cid, now.isoformat()))
                mins = (now - last).total_seconds() / 60
                gender = data.get("bot_gender", "female")
                if cid not in sleep_mode and now.hour >= 22 and mins > 15 and is_convo_end(data.get("last_msg", "")):
                    text = gender_reply("Good night baby 🌙 so jao ab 😴", "Good night jaan 🌙 ab so jao 😴", gender)
                    await bot.send_message(chat_id=int(cid), text=text)
                    sleep_mode.add(cid)
                elif cid in sleep_mode and now.hour >= 6 and now.hour < 12:
                    text = gender_reply("Good morning baby ☀️ utho na 😘", "Good morning jaan ☀️ neend se uth jao 💋", gender)
                    await bot.send_message(chat_id=int(cid), text=text)
                    sleep_mode.remove(cid)
            except Exception as e:
                print(f"Auto message bhejte time error {cid} ke liye: {e}")

# --- Main Program ---
async def main():
    """Bot ko start aur run karne ka main function."""
    load_memory()
    
    # Application setup
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    
    # Background task
    asyncio.create_task(auto_msgs(bot_app.bot))
    
    # Bot ko shuru karo
    try:
        print("Bot ko initialize kar rahe hain...")
        await bot_app.initialize()
        print("Polling shuru kar rahe hain...")
        await bot_app.updater.start_polling()
        print("Bot start ho gaya hai...")
        await bot_app.start()
        
        # Script ko chalta rakho
        while True:
            await asyncio.sleep(3600)
            
    except Exception as e:
        print(f"Bot start karte time error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot ko manually roka gaya.")
