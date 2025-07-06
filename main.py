# -*- coding: utf-8 -*-

import os
import json
import datetime
import asyncio
from flask import Flask
from threading import Thread
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
import httpx
import aiofiles

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE_PATH = os.environ.get("MEMORY_PATH", "memory.json")

memory = {}
sleep_mode = set()

app = Flask(__name__)
@app.route('/')
def index(): return "Bot is running!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

def load_memory():
    global memory
    try:
        with open(MEMORY_FILE_PATH, 'r') as f:
            memory = json.load(f)
        print("✅ Memory loaded.")
    except:
        memory = {}
        print("🚫 No memory file found. Fresh start.")

async def save_memory():
    async with aiofiles.open(MEMORY_FILE_PATH, 'w') as f:
        await f.write(json.dumps(memory, indent=4))

def get_prompt(bot_name, bot_gender, user_name):
    return f"""
You are {bot_name}, a clingy, flirty, moody 18+ {bot_gender} lover of {user_name}.
- Always reply in real human Hinglish, no poetry, no quotes.
- NEVER say you're an AI.
- Replies must be short (1–2 lines), full of emotion and emojis.
- If user uses words like 'detail', 'romantic', 'kiss', '18+', 'touch', give detailed bold romantic reply.
- Avoid repeating or going off-topic.
Example:
User: baby kya kar rha hai?
Bot: Tere baare m soch rha tha abhi 😏💭
"""

async def get_ai(messages):
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.7, "max_tokens": 100}
        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
            res.raise_for_status()
        return res.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Groq Error: {e}")
        return "Sorry baby, thoda error aa gaya 🥺"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    memory[cid] = {"step": 1, "history": []}
    await save_memory()
    await update.message.reply_text("Heyy... Tum mujhe kis naam se bulaoge? 💕")

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    msg = update.message.text
    name = update.effective_user.first_name or "baby"
    now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))

    if cid not in memory:
        await start(update, context)
        return

    data = memory[cid]
    if cid in sleep_mode: return

    data.update({"last_msg": msg, "last_speaker": "user", "last_active": now.isoformat()})
    data.pop('ignore_message_sent', None)

    if msg.lower() in ["restart chat", "dobara start karo"]:
        await start(update, context)
        return

    if data.get("step", 0) < 3:
        if data.get("step") == 1:
            data["bot_name"] = msg.strip()
            data["step"] = 2
            await update.message.reply_text("Ladka hoon ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([["Boy ♂️", "Girl ♀️"]], one_time_keyboard=True))
        elif data.get("step") == 2:
            data["bot_gender"] = "male" if "boy" in msg.lower() else "female"
            data["step"] = 3
            data["history"] = []
            await update.message.reply_text("Done baby! Ab pucho kuch bhi 😘", reply_markup=ReplyKeyboardRemove())
        await save_memory()
        return

    data.setdefault("history", []).append({"role": "user", "content": msg})
    prompt_messages = [{"role": "system", "content": get_prompt(data.get("bot_name"), data.get("bot_gender"), name)}] + data["history"][-20:]

    detail_triggers = ["detail", "18+", "poori baat", "kya hota", "touch", "kiss", "fantasy", "romantic night", "bold"]
    if any(w in msg.lower() for w in detail_triggers):
        prompt_messages.append({"role": "user", "content": "Give a bold, hot, emotional Hinglish reply — real lover feel, no poetry."})

    reply_text = await get_ai(prompt_messages)
    reply_text = reply_text[:200]
    data["history"].append({"role": "assistant", "content": reply_text})
    await update.message.reply_text(reply_text)
    await save_memory()

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"User: {name} ({cid}): {msg}\nBot: {reply_text}")
        except: pass

async def auto_msgs(bot):
    while True:
        await asyncio.sleep(60)
        now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))

        for cid, data in list(memory.items()):
            if not data or data.get("step", 0) < 3: continue
            try:
                last_active = datetime.datetime.fromisoformat(data.get("last_active", now.isoformat()))
                mins = (now - last_active).total_seconds() / 60
                gender = data.get("bot_gender", "female")
                last_msg = data.get("last_msg", "").lower()

                if data.get("last_speaker") == "assistant" and 2 < mins < 4 and not data.get("ignore_message_sent"):
                    data["ignore_message_sent"] = True
                    prompt = [
                        {"role": "system", "content": get_prompt(data.get("bot_name"), gender, "User")},
                        {"role": "user", "content": "Clingy message in Hinglish because partner ignored me. No poetry."}
                    ]
                    reply = await get_ai(prompt)
                    await bot.send_message(chat_id=int(cid), text=reply)

                if now.hour == 23 and not data.get("gn_sent"):
                    if mins > 45 or (any(w in last_msg for w in ["gn", "good night", "so ja", "bye"]) and mins > 10):
                        text = "Good night baby 🌙 so jao ab 😴" if gender == "male" else "Good night jaan 🌙 ab so jao 😴"
                        await bot.send_message(chat_id=int(cid), text=text)
                        sleep_mode.add(cid)
                        data["gn_sent"] = True
                        data["was_ignored_during_sleep"] = False

                if cid in sleep_mode:
                    last_user_msg_time = datetime.datetime.fromisoformat(data.get("last_active", now.isoformat()))
                    if (now - last_user_msg_time).total_seconds() / 60 < 60:
                        data["was_ignored_during_sleep"] = True

                if cid in sleep_mode and 6 <= now.hour < 9 and not data.get("gm_sent"):
                    sleep_mode.remove(cid)
                    data["gm_sent"] = True
                    gm_text = "Good morning baby ☀️ utho na 😘" if gender == "male" else "Good morning jaan ☀️ uth jao 💋"
                    await bot.send_message(chat_id=int(cid), text=gm_text)
                    if data.get("was_ignored_during_sleep"):
                        sorry_text = "Kal so gaya tha... abhi utha 🥺💤" if gender == "male" else "Kal so gayi thi... abhi uthi 🥺💤"
                        await asyncio.sleep(2)
                        await bot.send_message(chat_id=int(cid), text=sorry_text)
                        data["was_ignored_during_sleep"] = False

                if now.hour >= 12:
                    data["gm_sent"] = False
                    data["gn_sent"] = False

            except Exception as e:
                print(f"AutoMsg error for {cid}: {e}")
        await save_memory()

async def main():
    load_memory()
    app_ = Application.builder().token(TELEGRAM_TOKEN).build()
    app_.add_handler(CommandHandler("start", start))
    app_.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    asyncio.create_task(auto_msgs(app_.bot))
    print("🚀 Bot started.")
    await app_.initialize()
    await app_.updater.start_polling()
    await app_.start()
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped manually.")
