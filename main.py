# -*- coding: utf-8 -*-

import os
import json
import datetime
# 'import requests' waali line yahan se hata di gayi hai
import asyncio
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
import httpx      # Ye non-blocking requests ke liye hai
import aiofiles   # Ye files ko non-blocking tareeke se save karne ke liye hai

# --- Bot ki Settings ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE = "memory.json" # Bot ki yaadein is file mein save hongi

# --- Bot ki Yaaddasht ---
memory = {}
sleep_mode = set()
last_active = {}

def load_memory():
    # Bot start hone par purani yaadein load karo
    global memory
    try:
        with open(MEMORY_FILE, 'r') as f:
            memory = json.load(f)
    except FileNotFoundError:
        memory = {}
    except json.JSONDecodeError:
        memory = {}

# ASYNC: Yaaddasht save karo, bina bot ko roke
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
    # Ye prompt AI ko batata hai ki use kaisa behave karna hai
    return f"""
You are {bot_name}, a real human partner of {user_name}. You are a {bot_gender}.
You're romantic, clingy, 18+, flirty, emotional.
Style: Gen Z Hinglish, short replies, full mood swings.
Never say you're an AI.
"""

# ASYNC: AI se baat karo, bina bot ko roke
async def get_ai(messages):
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.8}
        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
            res.raise_for_status() # Agar koi error aaye API se to yahin pata chal jaayega
        return res.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Groq API mein Error: {e}")
        return "Kuch gadbad ho gayi baby 🥺"

# --- Time ke Helper Functions ---
def is_convo_end(msg):
    # Check karne ke liye ki user good night bol raha hai ya nahi
    text = msg.lower()
    return any(w in text for w in ["gn", "good night", "bye", "so ja", "so rha", "so rhi"])

def gender_reply(text_male, text_female, gender):
    # Bot ke gender ke hisaab se reply dene ke liye
    return text_male if gender == "male" else text_female

# --- Bot ke Handlers (Jo message handle karte hain) ---
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
        sleep_mode.remove(cid) # Ab user ne message kiya to neend se utha do
        return

    if msg.lower() == "restart chat":
        await start(update, context)
        return

    # --- Setup ke Steps ---
    if data.get("step") == 1: # Bot ka naam poochho
        data["bot_name"] = msg.strip()
        data["step"] = 2
        await save_memory()
        await update.message.reply_text("Ladka hoon ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([['Boy ♂️', 'Girl ♀️']], one_time_keyboard=True))
        return

    if data.get("step") == 2: # Bot ka gender poochho
        data["bot_gender"] = "male" if "boy" in msg.lower() else "female"
        data["step"] = 3
        data["history"] = []
        await save_memory()
        await update.message.reply_text("Done baby! Ab pucho kuch bhi 😘", reply_markup=ReplyKeyboardRemove())
        return

    # --- Normal Chat ---
    data.setdefault("history", []).append({"role": "user", "content": msg})
    prompt = [{"role": "system", "content": get_prompt(data.get("bot_name", "Baby"), data.get("bot_gender", "female"), name)}] + data["history"][-20:]
    
    reply = await get_ai(prompt)

    data["history"].append({"role": "assistant", "content": reply})
    memory[cid] = data
    await save_memory()

    await update.message.reply_text(reply)

    if ADMIN_CHAT_ID:
        try:
            # Admin ko har message ki khabar do
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"User: {name} ({cid}): {msg}\nBot: {reply}")
        except Exception as e:
            print(f"Admin ko log bhejte time error: {e}")

# --- Automatic Good Morning / Night wale Messages ---
async def auto_msgs(bot):
    while True:
        await asyncio.sleep(300) # Har 5 minute mein check karo
        now = datetime.datetime.now()
        
        # Dictionary ke items copy kar rahe hain taaki loop mein error na aaye
        for cid, data in list(memory.items()):
            try:
                last = datetime.datetime.fromisoformat(last_active.get(cid, now.isoformat()))
                mins = (now - last).total_seconds() / 60
                gender = data.get("bot_gender", "female")

                # Good night bhejne ka logic
                if cid not in sleep_mode and now.hour >= 22 and mins > 15 and is_convo_end(data.get("last_msg", "")):
                    text = gender_reply("Good night baby 🌙 so jao ab 😴", "Good night jaan 🌙 ab so jao 😴", gender)
                    await bot.send_message(chat_id=int(cid), text=text)
                    sleep_mode.add(cid)
                
                # Good morning bhejne ka logic
                elif cid in sleep_mode and now.hour >= 6 and now.hour < 12:
                    text = gender_reply("Good morning baby ☀️ utho na 😘", "Good morning jaan ☀️ neend se uth jao 💋", gender)
                    await bot.send_message(chat_id=int(cid), text=text)
                    sleep_mode.remove(cid)
            except Exception as e:
                print(f"Auto message bhejte time error {cid} ke liye: {e}")

# --- Main Program ---
async def runner():
    load_memory()
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    
    # Background task shuru karo
    asyncio.create_task(auto_msgs(bot_app.bot))
    
    print("Bot shuru ho raha hai...")
    await bot_app.run_polling()

if __name__ == "__main__":
    # Asyncio app chalane ka naya aur aasan tareeka
    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        print("Bot ko manually roka gaya.")
