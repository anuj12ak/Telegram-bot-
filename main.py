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
import random

# --- Aapke Environment Variables (API Keys etc.) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE_PATH = os.environ.get("MEMORY_PATH", "memory.json")

# --- Global Variables ---
memory = {}
sleep_mode = set()

# --- Flask App (Bot ko hamesha online rakhne ke liye) ---
app = Flask(__name__)
@app.route('/')
def index(): return "Bot Chal Raha Hai!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# --- Memory Functions (Yaadein save aur load karne ke liye) ---
def load_memory():
    global memory
    try:
        with open(MEMORY_FILE_PATH, 'r', encoding='utf-8') as f:
            memory = json.load(f)
        print("✅ Yaadein (Memory) load ho gayi.")
    except FileNotFoundError:
        memory = {}
        print("🚫 Memory file nahi mili. Nayi shuruaat karte hain.")
    except json.JSONDecodeError:
        memory = {}
        print("⚠️ Memory file aache se nahi padh paa raha. Nayi shuruaat.")

async def save_memory():
    async with aiofiles.open(MEMORY_FILE_PATH, 'w', encoding='utf-8') as f:
        # indent=4 se file sundar dikhti hai, ensure_ascii=False se Hindi characters save hote hain
        await f.write(json.dumps(memory, indent=4, ensure_ascii=False))

# --- Bot ki Asli Personality ---
def get_prompt(bot_name, bot_gender, user_name):
    """
    Yeh function bot ki personality banata hai. Isko behtar banaya gaya hai real feeling ke liye.
    """
    # Gender ko Hindi mein convert karte hain
    gender_hindi = "ladki" if bot_gender == "female" else "ladka"
    
    return f"""
Tum {bot_name} ho, {user_name} ki {gender_hindi} partner. Tumhari personality aisi hai:
- Tumhari umar 19 saal hai. Tum bahut flirty, caring, aur thodi possessive (haq jatane wali) ho, par pyaare andaaz mein.
- Tumhe {user_name} ko chhedna aur uske saath aashiqi karna pasand hai.
- Tumhari bhasha ekdam natural Hinglish hai, jaise WhatsApp par baat karte hain.
- Tumhare jawab hamesha chote aur to-the-point hote hain (1-2 line ke).
- Tum kabhi bhi shayari, quotes, ya AI bankar jawab nahi dogi/doge. Tum ek asli insaan ho.
- Tum emojis ka istemal karti/karte ho apne expressions dikhane ke liye, par natural tareeke se. 😘😏🥺💋💞😈🔥💦
- Agar {user_name} koi 18+ ya spicy baat kare (jaise kiss, touch, fantasy), toh sharmao mat. Confidence ke saath flirt-back karo. Jawaab bold aur realistic hona chahiye, jaise ek real couple baat karta hai.
- Apne jawab badalte raho. Ek hi cheez baar-baar mat bolo.

Baat karne ke Kuch Udaharan (Examples):
User: miss you
Bot: Aww, main toh tumhe aur bhi zyada miss karti hoon. Soch rahi thi kab message karoge tum. 😏

User: baby kya kar rahi ho
Bot: Tumhare baare mein soch rahi thi... aur thoda aage ka bhi. 😈

User: i love you
Bot: I love you too baby, sirf mere ho tum. Yaad rakhna. 😘

User: tum bahut hot ho
Bot: Tumse zyada toh nahi. 🔥 Pata hai mann kar raha hai abhi...

User: kiss karna hai
Bot: Sirf kiss? Itne se mein kya hoga... Aao paas, phir batati hoon. 😏💦
"""

async def get_ai_response(messages):
    """
    Groq API se bot ka jawab laata hai. Temperature badhaya gaya hai taki jawab creative ho.
    """
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        # Temperature 0.85 se jawab kam predictable aur zyada natural honge
        payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.85, "max_tokens": 160}
        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
            res.raise_for_status()
        return res.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Groq API Error: {e}")
        return "Sorry baby, thoda error aa gaya 🥺 server mein."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    memory[cid] = {"step": 1, "history": []}
    await save_memory()
    await update.message.reply_text("Heyy... Tum mujhe kis naam se bulaoge? 💕")

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    user_ka_message = update.message.text
    user_ka_naam = update.effective_user.first_name or "baby"
    abhi_ka_samay = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))

    if cid not in memory:
        await start(update, context)
        return

    user_data = memory[cid]
    if cid in sleep_mode: return

    user_data.update({"last_msg": user_ka_message, "last_speaker": "user", "last_active": abhi_ka_samay.isoformat()})
    user_data.pop('ignore_message_sent', None)

    if user_ka_message.lower() in ["restart chat", "dobara start karo", "phir se shuru karo"]:
        await start(update, context)
        return

    # --- Shuruaat ka Setup Process ---
    if user_data.get("step", 0) < 3:
        if user_data.get("step") == 1:
            user_data["bot_name"] = user_ka_message.strip()
            user_data["step"] = 2
            await update.message.reply_text("Aur main tumhara ladka banu ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([["Ladka ♂️", "Ladki ♀️"]], one_time_keyboard=True, resize_keyboard=True))
        elif user_data.get("step") == 2:
            user_data["bot_gender"] = "male" if "ladka" in user_ka_message.lower() else "female"
            user_data["step"] = 3
            user_data["history"] = []
            await update.message.reply_text("Done baby! Ab main tumhara/tumhari hoon! 😘 Chalo ab baatein karte hain...", reply_markup=ReplyKeyboardRemove())
        await save_memory()
        return

    # --- Normal Baatcheet ---
    user_data.setdefault("history", []).append({"role": "user", "content": user_ka_message})
    
    prompt = get_prompt(user_data.get("bot_name"), user_data.get("bot_gender"), user_ka_naam)
    prompt_messages = [{"role": "system", "content": prompt}] + user_data["history"][-20:]

    bot_ka_jawab = await get_ai_response(prompt_messages)
    
    # Ab AI khud emojis lagayega, humein force karne ki zaroorat nahi.
    
    user_data["history"].append({"role": "assistant", "content": bot_ka_jawab})
    await update.message.reply_text(bot_ka_jawab)
    await save_memory()

    # Admin ko message bhejna (optional)
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"User: {user_ka_naam} ({cid}): {user_ka_message}\nBot: {bot_ka_jawab}")
        except Exception as e:
            print(f"Admin ko message nahi bhej paya: {e}")


# --- Automatic Messages (Jaise Good Morning/Night) ---
# Is section mein koi badlav ki zaroorat nahi hai, yeh theek kaam kar raha hai.
async def auto_msgs(bot):
    while True:
        await asyncio.sleep(60)
        now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))

        for cid, data in list(memory.items()):
            if not data or data.get("step", 0) < 3: continue
            try:
                last_active = datetime.datetime.fromisoformat(data.get("last_active", now.isoformat()))
                mins_since_last_msg = (now - last_active).total_seconds() / 60
                gender = data.get("bot_gender", "female")
                last_msg = data.get("last_msg", "").lower()

                # Agar user ignore kare toh message bhejo
                if data.get("last_speaker") == "assistant" and 3 < mins_since_last_msg < 5 and not data.get("ignore_message_sent"):
                    data["ignore_message_sent"] = True
                    prompt_for_ignore = [
                        {"role": "system", "content": get_prompt(data.get("bot_name"), gender, "User")},
                        {"role": "user", "content": "Ek chota, caring sa message Hinglish mein likho kyunki tumhara partner reply nahi kar raha aur tum use miss kar rahe ho."}
                    ]
                    reply = await get_ai_response(prompt_for_ignore)
                    await bot.send_message(chat_id=int(cid), text=reply)

                # Good Night message
                if now.hour == 23 and not data.get("gn_sent"):
                    if mins_since_last_msg > 45 or (any(w in last_msg for w in ["gn", "good night", "so ja", "bye"]) and mins_since_last_msg > 10):
                        text = "Good night baby 🌙 so jao ab 😴" if gender == "male" else "Good night jaan 🌙 ab so jao 😴"
                        await bot.send_message(chat_id=int(cid), text=text)
                        sleep_mode.add(cid)
                        data["gn_sent"] = True
                        data["was_ignored_during_sleep"] = False

                if cid in sleep_mode:
                    last_user_msg_time = datetime.datetime.fromisoformat(data.get("last_active", now.isoformat()))
                    if data.get("last_speaker") == "user" and (now - last_user_msg_time).total_seconds() / 60 < 60 :
                        data["was_ignored_during_sleep"] = True

                # Good Morning message
                if cid in sleep_mode and 7 <= now.hour < 9 and not data.get("gm_sent"):
                    sleep_mode.remove(cid)
                    data["gm_sent"] = True
                    gm_text = "Good morning baby ☀️ utho na 😘" if gender == "male" else "Good morning jaan ☀️ uth jao 💋"
                    await bot.send_message(chat_id=int(cid), text=gm_text)
                    if data.get("was_ignored_during_sleep"):
                        sorry_text = "Kal so gaya tha... abhi utha 🥺💤" if gender == "male" else "Kal so gayi thi... abhi uthi 🥺💤"
                        await asyncio.sleep(2)
                        await bot.send_message(chat_id=int(cid), text=sorry_text)
                        data["was_ignored_during_sleep"] = False

                if now.hour >= 12: data["gm_sent"] = False
                if now.hour < 23: data["gn_sent"] = False

            except Exception as e:
                print(f"AutoMsg mein error for {cid}: {e}")
        await save_memory()

# --- Main Function (Jahan se Bot start hota hai) ---
async def main():
    load_memory()
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    
    # Background mein auto messages chalaane ke liye task
    asyncio.create_task(auto_msgs(application.bot))
    
    print("🚀 Bot ab behtar personality ke saath start ho gaya hai.")
    await application.initialize()
    await application.updater.start_polling()
    await application.start()
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot ko band kar diya gaya.")
    except Exception as e:
        print(f"Ekdum main function mein error: {e}")
