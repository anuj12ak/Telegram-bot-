import os
import json
import datetime
import requests
import asyncio
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# --- Config ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE = "memory.json"

# --- Memory ---
memory = {}
sleep_mode = set()
last_active = {}

def load_memory():
    global memory
    try:
        with open(MEMORY_FILE, 'r') as f:
            memory = json.load(f)
    except: memory = {}

def save_memory():
    with open(MEMORY_FILE, 'w') as f:
        json.dump(memory, f)

# --- Flask Server (Keep Alive) ---
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is running!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# --- Prompt & AI ---
def get_prompt(bot_name, bot_gender, user_name):
    return f"""
You are {bot_name}, a real human partner of {user_name}. You are a {bot_gender}.
You're romantic, clingy, 18+, flirty, emotional.
Style: Gen Z Hinglish, short replies, full mood swings.
Never say you're an AI.
"""

def get_ai(messages):
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.8}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        return res.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print("GROQ API Error:", e)
        return "Kuch gadbad ho gayi baby 🥺"

# --- Time Helpers ---
def is_convo_end(msg):
    text = msg.lower()
    return any(w in text for w in ["gn", "good night", "bye", "so ja", "so rha", "so rhi"])

def gender_reply(text_male, text_female, gender):
    return text_male if gender == "male" else text_female

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    memory[cid] = {"step": 1, "history": []}
    save_memory()
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
        return

    if msg.lower() == "restart chat":
        memory[cid] = {"step": 1, "history": []}
        save_memory()
        await update.message.reply_text("Chalo fir se shuru karte hain 💕")
        return

    if data.get("step") == 1:
        data["bot_name"] = msg.strip()
        data["step"] = 2
        save_memory()
        await update.message.reply_text("Ladka hoon ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([['Boy ♂️', 'Girl ♀️']], one_time_keyboard=True))
        return

    if data.get("step") == 2:
        data["bot_gender"] = "male" if "boy" in msg.lower() else "female"
        data["step"] = 3
        data["history"] = []
        save_memory()
        await update.message.reply_text("Done baby! Ab pucho kuch bhi 😘", reply_markup=ReplyKeyboardRemove())
        return

    data.setdefault("history", []).append({"role": "user", "content": msg})
    prompt = [{"role": "system", "content": get_prompt(data.get("bot_name", "Baby"), data.get("bot_gender", "female"), name)}] + data["history"][-20:]
    reply = get_ai(prompt)

    data["history"].append({"role": "assistant", "content": reply})
    memory[cid] = data
    save_memory()

    await update.message.reply_text(reply)

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"{name} ({cid}): {msg}\nBot: {reply}")
        except: pass

# --- Auto GM / GN ---
async def auto_msgs(bot):
    while True:
        await asyncio.sleep(300)
        now = datetime.datetime.now()
        for cid, data in memory.items():
            try:
                last = datetime.datetime.fromisoformat(last_active.get(cid, now.isoformat()))
                mins = (now - last).total_seconds() / 60
                gender = data.get("bot_gender", "female")
                if cid not in sleep_mode and now.hour == 23 and mins > 10 and is_convo_end(data.get("last_msg", "")):
                    text = gender_reply("Good night baby 🌙 so jao ab 😴", "Good night jaan 🌙 ab so jao 😴", gender)
                    await bot.send_message(chat_id=int(cid), text=text)
                    sleep_mode.add(cid)
                elif cid in sleep_mode and now.hour == 6 and mins > 120:
                    text = gender_reply("Good morning baby ☀️ utho na 😘", "Good morning jaan ☀️ neend se uth jao 💋", gender)
                    await bot.send_message(chat_id=int(cid), text=text)
                    sleep_mode.remove(cid)
            except Exception as e:
                print(f"AutoMsg Error for {cid}: {e}")

# --- Main ---
async def main():
    load_memory()
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    asyncio.create_task(auto_msgs(bot_app.bot))
    await bot_app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "already running" in str(e):
            import nest_asyncio
            nest_asyncio.apply()
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
        else:
            raise
