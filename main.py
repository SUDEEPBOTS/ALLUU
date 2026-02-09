import time
import requests
import random
import string
import asyncio
import os
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- 🛠 CONFIGURATION ---
# Heroku Config Vars se value uthayega
API_ID = int(os.getenv("API_ID", "33917975"))
API_HASH = os.getenv("API_HASH", "9ded8160307386acef2451d464e7a9b9")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN missing! Heroku Config Vars check kar.")

app = Client("render_pro_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

MAIL_TM_URL = "https://api.mail.tm"
RENDER_API_URL = "https://api.render.com/v1/owners"

# User Data store karne ke liye
user_sessions = {}

# --- 📧 MAIL FUNCTIONS ---
def get_mailtm_account():
    try:
        # Domain Fetch
        domain_resp = requests.get(f"{MAIL_TM_URL}/domains")
        if domain_resp.status_code != 200: return None
        
        # Random Domain Select
        domains = domain_resp.json()['hydra:member']
        if not domains: return None
        
        domain = random.choice(domains)['domain']
        
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        email = f"{username}@{domain}"
        password = "RenderPass" + ''.join(random.choices(string.digits, k=4)) + "!"
        
        # Account Create
        create_resp = requests.post(f"{MAIL_TM_URL}/accounts", json={"address": email, "password": password})
        if create_resp.status_code == 201:
            # Token Get
            token_resp = requests.post(f"{MAIL_TM_URL}/token", json={"address": email, "password": password})
            return email, password, token_resp.json()['token']
    except Exception as e:
        print(f"Mail Gen Error: {e}")
    return None, None, None

# --- 🤖 BOT COMMANDS ---

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "👋 **Render Pro Bot mein swagat hai!**\n\n"
        "Main tera kaam aasaan kar dunga:\n"
        "1. Fresh Email dunga.\n"
        "2. **Mail aate hi khud Verify kar dunga.**\n"
        "3. Tujhe seedha API Page pe bhejunga.\n"
        "4. Owner ID nikal ke dunga.\n\n"
        "👇 **Niche click karke start kar:**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Open Register Page", url="https://dashboard.render.com/register")],
            [InlineKeyboardButton("⚡ Generate Email", callback_data="gen_mail")]
        ])
    )

@app.on_callback_query(filters.regex("gen_mail"))
async def generate_mail(client, callback_query):
    chat_id = callback_query.message.chat.id
    
    await callback_query.message.edit_text("🔄 **Generating High-Quality Email...**")
    
    email, password, token = get_mailtm_account()
    
    if not email:
        await callback_query.message.edit_text(
            "❌ Server Error. Thodi der baad try kar.", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data="gen_mail")]])
        )
        return

    # Session Save
    user_sessions[chat_id] = {
        "email": email,
        "password": password,
        "step": "waiting_mail"
    }

    info_text = (
        f"🛠 **NEW IDENTITY CREATED**\n\n"
        f"📧 **Email:** `{email}`\n"
        f"🔑 **Pass:** `{password}`\n\n"
        "👉 **Tera Kaam:**\n"
        "1. Incognito Tab mein Register kar.\n"
        "2. Puzzle solve kar aur Submit daba.\n"
        "3. **Bas!** Fir yahan wapas aaja, main verify kar dunga.\n"
        "👀 **Checking Inbox...**"
    )
    
    msg = await callback_query.message.edit_text(info_text)
    
    # Background Mail Checker Start
    asyncio.create_task(check_inbox_loop(client, chat_id, token, msg))

# --- 📨 MAIL LOOP & AUTO VERIFY ---
async def check_inbox_loop(client, chat_id, token, message):
    headers = {"Authorization": f"Bearer {token}"}
    
    # 10 Minute wait karega
    for i in range(120): 
        try:
            if chat_id not in user_sessions: break

            resp = requests.get(f"{MAIL_TM_URL}/messages", headers=headers)
            if resp.status_code == 200:
                data = resp.json()['hydra:member']
                if data:
                    msg_id = data[0]['id']
                    full_msg = requests.get(f"{MAIL_TM_URL}/messages/{msg_id}", headers=headers).json()
                    
                    body = full_msg.get('text') or full_msg.get('html') or ""
                    
                    # --- AUTO VERIFY LOGIC ---
                    verify_link = None
                    if "https://dashboard.render.com/verify-email" in body:
                        # Regex se Link nikalenge
                        match = re.search(r'https://dashboard\.render\.com/verify-email[^"\s<>]*', body)
                        if match:
                            verify_link = match.group(0)
                            
                            # Bot khud click karega (GET Request)
                            verify_msg = "⚠️ Auto-Click Failed"
                            try:
                                requests.get(verify_link, timeout=10)
                                verify_msg = "✅ **Email Auto-Verified!**"
                            except:
                                pass

                            # User ko update do + Direct Link do
                            await message.edit_text(
                                f"📩 **MAIL RECEIVED**\n\n"
                                f"{verify_msg}\n"
                                f"Maine link click kar diya hai. Account Active hai!\n\n"
                                "👇 **STEP 2: API KEY**\n"
                                "1. Niche button daba, seedha Settings khulegi.\n"
                                "2. 'Create API Key' daba.\n"
                                "3. Key copy karke yahan bhej (starts with `rnd_`).",
                                reply_markup=InlineKeyboardMarkup([
                                    # YAHAN HAI MAGIC LINK - Seedha API Page
                                    [InlineKeyboardButton("🔗 Go to API Settings", url="https://dashboard.render.com/u/me/keys")]
                                ])
                            )
                            
                            user_sessions[chat_id]['step'] = 'waiting_api'
                            return 
        except:
            pass
        
        await asyncio.sleep(5)

# --- 🔑 API HANDLING & OWNER ID FETCH ---
@app.on_message(filters.text & ~filters.command("start"))
async def handle_api_input(client, message):
    chat_id = message.chat.id
    api_key = message.text.strip()

    # Check valid session step
    if chat_id not in user_sessions or user_sessions[chat_id].get('step') != 'waiting_api':
        return 

    # Basic Validation
    if not api_key.startswith("rnd_"):
        await message.reply_text("⚠️ **Invalid API Key!**\n `rnd_` se start hona chahiye.")
        return

    wait_msg = await message.reply_text("🔄 **Fetching Owner ID...**")

    # Fetch Owner ID
    try:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        response = requests.get(RENDER_API_URL, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            # Owner ID Extraction
            owner_id = "Unknown"
            if isinstance(data, list) and len(data) > 0:
                owner_id = data[0]['owner']['id']
            
            email = user_sessions[chat_id]['email']
            password = user_sessions[chat_id]['password']

            # 🔥 FINAL RESULT BLOCK (Small Letters)
            final_text = (
                "✅ **ALL SET! COPY KAR LO**\n\n"
                "👇 **Click to Copy All:**\n"
                f"```\n"
                f"email={email}\n"
                f"password={password}\n"
                f"owner_id={owner_id}\n"
                f"render_api_key={api_key}\n"
                f"```\n\n"
                "👆 **Ab bot deploy kar de!**"
            )
            
            await wait_msg.edit_text(
                final_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Start New", callback_data="gen_mail")]
                ])
            )
            
            del user_sessions[chat_id]
            
        else:
            await wait_msg.edit_text(
                f"❌ **Error:** {response.status_code}\nAPI Key galat lag rahi hai.",
                reply_markup=InlineKeyboardMarkup([
                     [InlineKeyboardButton("🔄 Retry", callback_data="gen_mail")]
                ])
            )

    except Exception as e:
        await wait_msg.edit_text(f"❌ **Crash:** {str(e)}")

print("🤖 HEROKU BOT STARTED!")
app.run()
