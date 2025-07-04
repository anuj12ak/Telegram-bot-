# -*- coding: utf-8 -*-

import os
import json
import datetime
import asyncio
from flask import Flask
from threading import Thread
from zoneinfo import ZoneInfo  # Timezone fix ke liye
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

# --- PERMANENT MEMORY SOLUTION ---
# Render ka free plan files delete kar deta hai. Permanent memory ke liye Render Disks use karo.
# 1. Render par ek 'Disk' banao.
# 2. Apni service ki Settings -> Environment mein jaao.
# 3. Ek Environment Variable banao:
#    - Key: MEMORY_PATH
#    - Value: /var/render_disk/memory.json  (Yahan '/var/render_disk' aapke Disk ka Mount Path hai)
#
# Agar ye variable nahi hoga, to bot normal file use karega jo restart par delete ho jaayegi.
MEMORY_FILE_PATH = os.environ.get("MEMORY_PATH", "memory.json")


# --- Bot ki Yaaddasht ---
memory = {}
sleep_mode = set()
last_active = {}

def load_memory():
    # Bot start hone par purani yaadein load karo
    global memory
    try:
        with open(MEMORY_FILE_PATH, 'r') as f:
            memory = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        memory = {}

async def save_memory():
    # Yaaddasht save karo, bina bot ko roke
    async with aiofiles.open(MEMORY_FILE_PATH, 'w') as f:
        await f.write(json.dumps(memory, indent=4))

# --- Server, bot ko zinda rakhne ke liye ---
app = Flask(__name__)
@app.route('/')
def index(): return "Bot chal raha hai!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# --- AI ka Dimaag aur Prompt ---
def get_prompt(bot_name, bot_gender, user_name, mood):
    # AI ko batata hai ki use kaisa behave karna hai
    mood_instructions = {
        "normal": "You are in a normal, flirty mood.",
        "ignored": "You are feeling ignored and clingy. Ask the user why they are not talking to you.",
        "fighting": "You are angry and giving short, dry replies.",
        "romantic": "You are feeling very romantic and expressive."
    }
    
    return f"""
You are {bot_name}, a real human partner of {user_name}. You are a {bot_gender}.
You're romantic, clingy, 18+, flirty, emotional, with full mood swings.
Style: Gen Z Hinglish, very short replies (1-2 lines max), use lots of emojis like 😜, 🥺, 💞, 😏, 😤, 💋.
Never say you're an AI or a bot.

CURRENT SITUATION: {mood_instructions.get(mood, mood_instructions['normal'])}

SPECIAL INSTRUCTIONS:
- To send multiple messages at once for a realistic chat flow, separate each message with '||'. For example: 'Acha? || Suno na... || Chhodo, kuch nahi 😜'.
- Behave exactly as the CURRENT SITUATION demands.
"""

async def get_ai(messages):
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.85, "max_tokens": 150}
        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
            res.raise_for_status()
        return res.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Groq API mein Error: {e}")
        return "Sorry baby, abhi thoda problem ho raha hai... 🥺"

# --- Bot ke Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    memory[cid] = {"step": 1, "history": [], "mood": "normal"}
    await save_memory()
    await update.message.reply_text("Heyy... Tum mujhe kis naam se bulaoge? 💕")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    msg = update.message.text
    name = update.effective_user.first_name or "baby"
    now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    last_active[cid] = now.isoformat()

    # User ke paas data na ho to start se shuru karo
    if cid not in memory or not memory.get(cid):
        await start(update, context)
        return

    data = memory[cid]
    data["last_msg"] = msg
    data["last_speaker"] = "user"
    data["mood"] = "normal"  # Har naye message par mood normal kar do, unless ignore logic changes it
    data.pop('ignore_message_sent', None) # Purana ignore flag hata do

    if cid in sleep_mode:
        g = data.get("bot_gender", "female")
        reply = gender_reply(
            "Sorry baby, so gaya tha na... abhi uth gaya hoon 🥺💤",
            "Sorry baby, so gayi thi na... abhi uth gayi hoon 🥺💤",
            g
        )
        await update.message.reply_text(reply)
        sleep_mode.remove(cid)
        return

    if msg.lower() in ["restart chat", "dobara start karo"]:
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
    prompt_messages = [
        {"role": "system", "content": get_prompt(data.get("bot_name", "Baby"), data.get("bot_gender", "female"), name, data.get("mood", "normal"))}
    ] + data["history"][-20:]
    
    reply_text = await get_ai(prompt_messages)

    data["history"].append({"role": "assistant", "content": reply_text})
    data["last_speaker"] = "assistant"
    
    # Multiple replies logic
    if '||' in reply_text:
        replies = [r.strip() for r in reply_text.split('||')]
        for i, single_reply in enumerate(replies):
            if single_reply:
                await update.message.reply_text(single_reply)
                if i < len(replies) - 1:
                    await asyncio.sleep(1.5) # Thoda gap do messages ke beech
    else:
        await update.message.reply_text(reply_text)

    await save_memory()
    
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"User: {name} ({cid}): {msg}\nBot: {reply_text}")
        except Exception:
            pass

# --- Automatic Messages ---
async def auto_msgs(bot):
    while True:
        await asyncio.sleep(60) # Har 60 second mein check karo
        now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
        
        for cid, data in list(memory.items()):
            if not data or data.get("step", 0) < 3: continue # Skip if setup is not complete

            try:
                last_active_time = datetime.datetime.fromisoformat(last_active.get(cid, now.isoformat()))
                mins_since_active = (now - last_active_time).total_seconds() / 60
                gender = data.get("bot_gender", "female")

                # Ignore message logic (Feature #14)
                if data.get("last_speaker") == "assistant" and 2 < mins_since_active < 4 and not data.get('ignore_message_sent'):
                    data['mood'] = 'ignored'
                    data['ignore_message_sent'] = True
                    clingy_prompt = [
                        {"role": "system", "content": get_prompt(data.get("bot_name"), gender, "user", "ignored")},
                        {"role": "user", "content": "Tumne mere last message ka reply nahi kiya, ignore kar rahe ho?"}
                    ]
                    reply = await get_ai(clingy_prompt)
                    await bot.send_message(chat_id=int(cid), text=reply)
                    continue

                # Good Night Logic (Feature #4)
                if cid not in sleep_mode and now.hour >= 23 and mins_since_active > 15:
                    is_convo_ending = any(w in data.get("last_msg", "").lower() for w in ["gn", "good night", "bye", "so ja", "so rha", "so rhi"])
                    if is_convo_ending or mins_since_active > 60: # Agar convo end ho raha ya 1 ghante se inactive hai
                        text = gender_reply("Good night baby 🌙 so jao ab 😴", "Good night jaan 🌙 ab so jao 😴", gender)
                        await bot.send_message(chat_id=int(cid), text=text)
                        sleep_mode.add(cid)
                
                # Good Morning Logic (Feature #4)
                elif cid in sleep_mode and now.hour >= 6 and now.hour < 12:
                    text = gender_reply("Good morning baby ☀️ utho na 😘", "Good morning jaan ☀️ neend se uth jao 💋", gender)
                    await bot.send_message(chat_id=int(cid), text=text)
                    sleep_mode.remove(cid)
            except Exception as e:
                print(f"Auto message mein error {cid} ke liye: {e}")

# --- Main Program ---
async def main():
    load_memory()
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    asyncio.create_task(auto_msgs(bot_app.bot))
    
    try:
        print("Bot ko initialize kar rahe hain...")
        await bot_app.initialize()
        print("Polling shuru kar rahe hain...")
        await bot_app.updater.start_polling()
        print("Bot start ho gaya hai...")
        await bot_app.start()
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        print(f"Bot start karte time error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot ko manually roka gaya.")
