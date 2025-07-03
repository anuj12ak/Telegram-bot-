import os
import json
import requests
import datetime
import asyncio
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)

# --- Flask Keep-Alive ---
flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Bot is running on Render!"

def run_flask(): flask_app.run(host="0.0.0.0", port=8080)
Thread(target=run_flask).start()

# --- Config ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE = "memory.json"

memory = {}
last_active = {}
sleep_mode = set()

def load_memory():
    global memory
    try:
        with open(MEMORY_FILE, 'r') as f:
            memory = json.load(f)
    except:
        memory = {}

def save_memory():
    with open(MEMORY_FILE, 'w') as f:
        json.dump(memory, f)

load_memory()

def get_system_prompt(bot_name, bot_gender, user_name):
    return f"""
You are {bot_name}, a real human partner of {user_name}. You are a {bot_gender}.
You're romantic, clingy, 18+, flirty, emotional.
Style: Gen Z Hinglish, short replies, full mood swings.
Never say you're an AI.
"""

def get_ai(messages):
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL_NAME, "messages": messages}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        return res.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print("GROQ API Error:", e)
        return "Kuch gadbad ho gayi baby 🥺"

def is_convo_end(text):
    text = text.lower()
    return any(w in text for w in ["good night", "gn", "bye", "so rha", "so rhi", "sleep"])

async def auto_messenger(app):
    while True:
        now = datetime.datetime.now()
        for cid, data in memory.items():
            last = last_active.get(cid)
            if not last: continue
            mins = (now - datetime.datetime.fromisoformat(last)).total_seconds() / 60
            gender = data.get("bot_gender", "female")

            if cid not in sleep_mode:
                if now.hour == 23 and mins > 10 and is_convo_end(data.get("last_msg", "")):
                    text = "Good night baby 🌙 so jao ab 😴" if gender == "male" else "Good night jaanu 🌙 ab so jao meri jaan 😴"
                    await app.bot.send_message(chat_id=int(cid), text=text)
                    sleep_mode.add(cid)
            else:
                if now.hour == 6 and mins > 120:
                    text = "Good morning baby ☀️ utho na 😘" if gender == "male" else "Good morning jaan ☀️ neend se uth jao ab 💋"
                    await app.bot.send_message(chat_id=int(cid), text=text)
                    sleep_mode.remove(cid)
        await asyncio.sleep(300)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    memory[cid] = {"step": 1, "history": []}
    save_memory()
    await update.message.reply_text("Hey! Tum mujhe kis naam se bulaoge? 💕")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    user_msg = update.message.text
    user_name = update.effective_user.first_name or "baby"
    now = datetime.datetime.now().isoformat()
    last_active[cid] = now
    data = memory.get(cid, {"step": 1})
    data["last_msg"] = user_msg

    if cid in sleep_mode:
        gender = memory.get(cid, {}).get("bot_gender", "female")
        text = "So gaya tha baby 🌙 ab baad me baat karte hain 🥺" if gender == "male" else "So gayi thi baby 🌙 baad me baat karte hain 🥺"
        await update.message.reply_text(text)
        return

    if user_msg.lower() == "restart chat":
        memory[cid] = {"step": 1, "history": []}
        save_memory()
        await update.message.reply_text("Chalo fir se shuru karte hain 💕")
        return

    if data.get("step") == 1:
        data["bot_name"] = user_msg.strip()
        data["step"] = 2
        memory[cid] = data
        save_memory()
        await update.message.reply_text("Ladka hoon ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([["Boy ♂️", "Girl ♀️"]], one_time_keyboard=True, resize_keyboard=True))
        return

    if data.get("step") == 2:
        data["bot_gender"] = "male" if "Boy" in user_msg else "female"
        data["step"] = 3
        data["history"] = []
        memory[cid] = data
        save_memory()
        await update.message.reply_text("Done baby! Ab pucho kuch bhi 😘", reply_markup=ReplyKeyboardRemove())
        return

    data.setdefault("history", []).append({"role": "user", "content": user_msg})
    prompt = [{"role": "system", "content": get_system_prompt(data['bot_name'], data['bot_gender'], user_name)}] + data["history"]
    reply = get_ai(prompt)
    data["history"].append({"role": "assistant", "content": reply})
    data["history"] = data["history"][-20:]
    memory[cid] = data
    save_memory()

    await update.message.reply_text(reply)
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"{user_name}: {user_msg}\nBot: {reply}")
        except: pass

async def run_bot():
    print("run_bot() started ✅")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    asyncio.create_task(auto_messenger(app))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(run_bot())
