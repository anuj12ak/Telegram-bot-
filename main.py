import os
import json
import requests
from flask import Flask
from threading import Thread
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)

# --- Keep Alive Server (Flask) ---
flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Bot is alive 💓"
def run_flask(): flask_app.run(host="0.0.0.0", port=8080)
Thread(target=run_flask).start()

# --- Config ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
MODEL = "llama3-70b-8192"
MEMORY_FILE = "memory.json"

memory = {}
try:
    with open(MEMORY_FILE, 'r') as f:
        memory = json.load(f)
except: pass

def save_memory(): 
    with open(MEMORY_FILE, 'w') as f:
        json.dump(memory, f)

def get_prompt(bot_name, gender, user_name):
    return f"You are {bot_name}, {user_name} ka real partner. You're a {gender}. Clingy, moody, flirty, romantic. Never say you're AI. Talk in Gen Z Hinglish. Short replies."

def get_ai(messages):
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "messages": messages}
        )
        return r.json()['choices'][0]['message']['content'].strip()
    except:
        return "API down hai baby 🥺"

# --- Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    memory[cid] = {"step": 1, "history": []}
    save_memory()
    await update.message.reply_text("Heyy... Tum mujhe kis naam se bulaoge? 💕")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    text = update.message.text
    user = update.effective_user.first_name or "baby"
    data = memory.get(cid, {"step": 1})

    if data["step"] == 1:
        data["bot_name"] = text
        data["step"] = 2
        memory[cid] = data
        save_memory()
        await update.message.reply_text("Ladka hoon ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([["Boy ♂️", "Girl ♀️"]], one_time_keyboard=True))
        return

    if data["step"] == 2:
        data["bot_gender"] = "male" if "boy" in text.lower() else "female"
        data["step"] = 3
        memory[cid] = data
        save_memory()
        await update.message.reply_text("Ho gaya baby 😘 ab kuch bhi bol sakte ho", reply_markup=ReplyKeyboardRemove())
        return

    # Chat mode
    prompt = [{"role": "system", "content": get_prompt(data["bot_name"], data["bot_gender"], user)}] + data.get("history", [])
    prompt.append({"role": "user", "content": text})
    reply = get_ai(prompt)
    data.setdefault("history", []).append({"role": "user", "content": text})
    data["history"].append({"role": "assistant", "content": reply})
    data["history"] = data["history"][-20:]
    memory[cid] = data
    save_memory()

    await update.message.reply_text(reply)
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"{user} said:\n{text}\n\nBot replied:\n{reply}")
        except: pass

# --- Main Entry ---
def main():
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    print("Bot deployed successfully ✅")
    bot_app.run_polling()

if __name__ == "__main__":
    main()
