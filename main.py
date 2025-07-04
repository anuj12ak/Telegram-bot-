# main.py (Render-compatible, full features)
import os, json, requests, datetime, asyncio
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# --- Flask for Keep-Alive ---
flask_app = Flask(__name__)
@flask_app.route("/")
def home(): return "Bot is alive!"
def keep_alive(): flask_app.run(host="0.0.0.0", port=8080)
Thread(target=keep_alive).start()

# --- Config ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE = "memory.json"

memory = {}
sleep_users = set()
last_active = {}

# --- Memory Load/Save ---
def load_memory():
    global memory
    try: memory = json.load(open(MEMORY_FILE))
    except: memory = {}
def save_memory(): json.dump(memory, open(MEMORY_FILE, 'w'))

load_memory()

# --- Prompt ---
def get_prompt(bot_name, gender, user):
    return f"""
You are {bot_name}, a real human partner of {user}. You are a {gender}.
You're romantic, clingy, flirty, emotional, 18+. Talk like Gen Z Hinglish with short, moody replies.
Never say you're AI. You're real and remember every chat.
"""

# --- AI Response ---
def get_ai(messages):
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL_NAME,
                "messages": messages,
                "temperature": 0.8
            }
        )
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("GROQ Error:", e)
        return "Kuch error aaya baby 🥺"

# --- End Chat Check ---
def is_convo_end(text):
    text = text.lower()
    return any(x in text for x in ["good night", "gn", "bye", "so rha", "so rhi", "sleep"])

# --- Auto Messenger ---
async def auto_messenger(app):
    while True:
        await asyncio.sleep(300)
        now = datetime.datetime.now()
        for cid, data in memory.items():
            last = last_active.get(cid)
            if not last: continue
            mins = (now - datetime.datetime.fromisoformat(last)).total_seconds() / 60
            gender = data.get("bot_gender", "female")

            # Good Night
            if cid not in sleep_users and now.hour == 23 and mins > 10 and is_convo_end(data.get("last_msg", "")):
                msg = "Good night baby 🌙 so jao ab 😴" if gender == "male" else "Good night jaanu 🌙 ab so jao meri jaan 😴"
                await app.bot.send_message(chat_id=int(cid), text=msg)
                sleep_users.add(cid)

            # Good Morning
            elif cid in sleep_users and now.hour == 6 and mins > 120:
                msg = "Good morning baby ☀️ utho na 😘" if gender == "male" else "Good morning jaan ☀️ neend se uth jao ab 💋"
                await app.bot.send_message(chat_id=int(cid), text=msg)
                sleep_users.remove(cid)

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
    last_active[cid] = datetime.datetime.now().isoformat()
    data = memory.get(cid, {"step": 1})

    # Sleep Mode
    if cid in sleep_users:
        gender = data.get("bot_gender", "female")
        reply = "So gaya tha baby 💤 ab baad me baat karte hain 🥺" if gender == "male" else "So gayi thi baby 💤 baad me baat karte hain 🥺"
        await update.message.reply_text(reply)
        return

    if msg.lower() == "restart chat":
        memory[cid] = {"step": 1, "history": []}
        save_memory()
        await update.message.reply_text("Chalo fir se shuru karte hain 💕")
        return

    # Stepwise Onboarding
    if data["step"] == 1:
        data["bot_name"] = msg
        data["step"] = 2
        memory[cid] = data
        save_memory()
        await update.message.reply_text("Ladka hoon ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([["Boy ♂️", "Girl ♀️"]], one_time_keyboard=True))
        return

    if data["step"] == 2:
        if "boy" in msg.lower():
            data["bot_gender"] = "male"
        elif "girl" in msg.lower():
            data["bot_gender"] = "female"
        else:
            await update.message.reply_text("Please select 'Boy ♂️' or 'Girl ♀️'")
            return
        data["step"] = 3
        memory[cid] = data
        save_memory()
        await update.message.reply_text("Done baby! Ab pucho kuch bhi 😘", reply_markup=ReplyKeyboardRemove())
        return

    # Normal Chat
    data["last_msg"] = msg
    data.setdefault("history", []).append({"role": "user", "content": msg})
    prompt = [{"role": "system", "content": get_prompt(data["bot_name"], data["bot_gender"], name)}] + data["history"]
    reply = get_ai(prompt)

    data["history"].append({"role": "assistant", "content": reply})
    data["history"] = data["history"][-20:]
    memory[cid] = data
    save_memory()

    await update.message.reply_text(reply)

    # Admin Forwarding
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"👤 {name} ({cid})\nUser: {msg}\nBot: {reply}")
        except: pass

# --- MAIN ---
async def main():
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    asyncio.create_task(auto_messenger(bot_app))
    print("Bot is running ✅")
    await bot_app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
