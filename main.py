# ✅ Final VibeMate Telegram Bot Code
# Features: Mood-based replies, short Hinglish flirty tone, memory, admin logging, sleep logic

import os
import json
import datetime
import asyncio
from flask import Flask
from threading import Thread
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import httpx
import aiofiles

# --- ENV Settings ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE_PATH = os.getenv("MEMORY_PATH", "memory.json")

# --- State ---
memory = {}
sleep_mode = set()
last_active = {}
last_bot_replies = {}

# --- Load & Save Memory ---
def load_memory():
    global memory
    try:
        with open(MEMORY_FILE_PATH, 'r') as f:
            memory = json.load(f)
    except:
        memory = {}

async def save_memory():
    async with aiofiles.open(MEMORY_FILE_PATH, 'w') as f:
        await f.write(json.dumps(memory, indent=4))

# --- Flask Keep-Alive ---
app = Flask(__name__)
@app.route('/')
def index(): return "VibeMate Bot Active!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# --- Prompt Builder ---
def get_prompt(bot_name, bot_gender, user_name):
    return f"""
You are {bot_name}, a {bot_gender} partner of {user_name}.
Your replies must be:
- 1-2 lines only
- Short, flirty Hinglish
- Use emoji (🥺😏😘💋💕💦)
- Sound like a clingy lover (not AI)
- Speak in present, realistic, emotional tone
- If user says: "Detail mein batao", reply full romantic/18+ details
Avoid repetition. Reply like real human partner.
"""

async def get_ai(messages):
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.7, "max_tokens": 80}
        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
            return res.json()['choices'][0]['message']['content'].strip()
    except:
        return "Sorry baby, thoda issue ho gaya... 🥺"

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    memory[cid] = {"step": 1, "history": []}
    await save_memory()
    await update.message.reply_text("Heyy... Tum mujhe kis naam se bulaoge? 💕")

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    msg = update.message.text.strip()
    name = update.effective_user.first_name or "baby"
    now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    last_active[cid] = now.isoformat()

    if cid not in memory:
        await start(update, context)
        return

    data = memory[cid]
    if data.get("step") == 1:
        data["bot_name"] = msg
        data["step"] = 2
        await update.message.reply_text("Ladka hoon ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([["Boy ♂️", "Girl ♀️"]], one_time_keyboard=True))
    elif data.get("step") == 2:
        data["bot_gender"] = "male" if "boy" in msg.lower() else "female"
        data["step"] = 3
        data["history"] = []
        await update.message.reply_text("Done baby! Ab pucho kuch bhi 😘", reply_markup=ReplyKeyboardRemove())
    else:
        data.setdefault("history", []).append({"role": "user", "content": msg})
        prompt = [{"role": "system", "content": get_prompt(data['bot_name'], data['bot_gender'], name)}] + data['history'][-20:]

        reply = await get_ai(prompt)
        for _ in range(2):  # retry if duplicate
            if cid in last_bot_replies and reply == last_bot_replies[cid]:
                reply = await get_ai(prompt)
            else:
                break

        data['history'].append({"role": "assistant", "content": reply})
        last_bot_replies[cid] = reply

        await update.message.reply_text(reply)
        if ADMIN_CHAT_ID:
            try:
                await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"User: {name} ({cid}): {msg}\nBot: {reply}")
            except: pass

    await save_memory()

# --- Auto Messages ---
async def auto_msgs(bot):
    while True:
        await asyncio.sleep(60)
        now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))

        for cid, data in memory.items():
            if data.get("step") < 3: continue
            try:
                last_time = datetime.datetime.fromisoformat(last_active.get(cid, now.isoformat()))
                mins = (now - last_time).total_seconds() / 60
                gender = data.get("bot_gender", "female")
                msg = data.get("last_msg", "")

                if data.get("last_speaker") == "assistant" and 3 < mins < 6 and not data.get("ignored_msg"):
                    data['ignored_msg'] = True
                    clingy = [
                        {"role": "system", "content": get_prompt(data['bot_name'], gender, "User")},
                        {"role": "user", "content": "Generate a clingy, emotional message because partner is ignoring me."}
                    ]
                    reply = await get_ai(clingy)
                    await bot.send_message(chat_id=int(cid), text=reply)

                if now.hour == 23 and cid not in sleep_mode and ("gn" in msg.lower() or "night" in msg.lower()) and mins > 10:
                    await bot.send_message(chat_id=int(cid), text="Good night jaan 🌙 ab so jao 😴")
                    sleep_mode.add(cid)
                    data["went_to_sleep"] = now.isoformat()

                if cid in sleep_mode and 6 <= now.hour < 10:
                    sleep_mode.remove(cid)
                    await bot.send_message(chat_id=int(cid), text="Good morning jaan ☀️ utho na 😘")
                    sleep_time = datetime.datetime.fromisoformat(data.get("went_to_sleep", now.isoformat()))
                    if last_time > sleep_time:
                        await asyncio.sleep(2)
                        await bot.send_message(chat_id=int(cid), text="Sorry baby, kal so gaya tha... abhi utha 🥺💤")

            except Exception as e:
                print(f"Auto-msg error for {cid}: {e}")

# --- Main ---
async def main():
    load_memory()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    asyncio.create_task(auto_msgs(app.bot))

    await app.initialize()
    await app.updater.start_polling()
    await app.start()
    print("VibeMate is live!")
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
