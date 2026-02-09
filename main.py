import time
import requests
import random
import string
import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- 🛠 CONFIGURATION ---

# 1. API ID & Hash (Defaults included, or set in Heroku)
API_ID = int(os.getenv("API_ID", "33917975"))
API_HASH = os.getenv("API_HASH", "9ded8160307386acef2451d464e7a9b9")

# 2. BOT TOKEN (MUST be in Heroku Config Vars)
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN missing! Add it to Heroku Config Vars.")

app = Client("render_pro_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

MAIL_TM_URL = "https://api.mail.tm"
RENDER_API_URL = "https://api.render.com/v1/owners"

# Temporary User Session Storage
user_sessions = {}

# --- 📧 MAIL FUNCTIONS ---
def get_mailtm_account():
    try:
        # Fetch Domains
        domain_resp = requests.get(f"{MAIL_TM_URL}/domains")
        if domain_resp.status_code != 200: return None
        
        # Select Random Domain to avoid blocks
        domains = domain_resp.json()['hydra:member']
        if not domains: return None
        
        domain = random.choice(domains)['domain']
        
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        email = f"{username}@{domain}"
        password = "RenderPass" + ''.join(random.choices(string.digits, k=4)) + "!"
        
        # Create Account
        create_resp = requests.post(f"{MAIL_TM_URL}/accounts", json={"address": email, "password": password})
        if create_resp.status_code == 201:
            # Get Token
            token_resp = requests.post(f"{MAIL_TM_URL}/token", json={"address": email, "password": password})
            return email, password, token_resp.json()['token']
    except Exception as e:
        print(f"Mail Gen Error: {e}")
    return None, None, None

# --- 🤖 BOT COMMANDS ---

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "👋 **Welcome to Render Pro Bot!**\n\n"
        "I will automate your Render Account Setup.\n"
        "1. I will provide a High-Quality Email.\n"
        "2. I will show the Verification Mail here.\n"
        "3. I will extract the Owner ID from your API Key.\n\n"
        "👇 **Click below to start:**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Go to Register Page", url="https://dashboard.render.com/register")],
            [InlineKeyboardButton("⚡ Generate Fresh Email", callback_data="gen_mail")]
        ])
    )

@app.on_callback_query(filters.regex("gen_mail"))
async def generate_mail(client, callback_query):
    chat_id = callback_query.message.chat.id
    
    await callback_query.message.edit_text("🔄 **Generating High-Quality Email...**")
    
    email, password, token = get_mailtm_account()
    
    if not email:
        await callback_query.message.edit_text(
            "❌ Server Error (Mail.tm). Please try again later.", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data="gen_mail")]])
        )
        return

    # Save Session
    user_sessions[chat_id] = {
        "email": email,
        "password": password,
        "step": "waiting_mail"
    }

    info_text = (
        f"🛠 **NEW IDENTITY CREATED**\n\n"
        f"📧 **Email:** `{email}`\n"
        f"🔑 **Pass:** `{password}`\n\n"
        "👉 **Steps:**\n"
        "1. Go to Render, Register using these details.\n"
        "2. Solve the Puzzle and Submit.\n"
        "3. Wait here for the Verification Mail.\n"
        "👀 **Checking Inbox...**"
    )
    
    msg = await callback_query.message.edit_text(info_text)
    
    # Start Background Mail Checker
    asyncio.create_task(check_inbox_loop(client, chat_id, token, msg))

# --- 📨 MAIL LOOP ---
async def check_inbox_loop(client, chat_id, token, message):
    headers = {"Authorization": f"Bearer {token}"}
    
    # Wait for 10 Minutes (120 * 5 sec)
    for i in range(120): 
        try:
            if chat_id not in user_sessions: break

            resp = requests.get(f"{MAIL_TM_URL}/messages", headers=headers)
            if resp.status_code == 200:
                data = resp.json()['hydra:member']
                if data:
                    msg_id = data[0]['id']
                    full_msg = requests.get(f"{MAIL_TM_URL}/messages/{msg_id}", headers=headers).json()
                    
                    subject = full_msg.get('subject', 'No Subject')
                    body = full_msg.get('text') or full_msg.get('html') or "Empty Body"
                    
                    # Truncate if too long for Telegram
                    if len(body) > 3500: body = body[:3500] + "...(truncated)"

                    await message.edit_text(
                        f"📩 **MAIL RECEIVED!**\n\n"
                        f"**Subject:** {subject}\n"
                        f"---------------------------------\n"
                        f"{body}\n"
                        f"---------------------------------\n\n"
                        "👆 **Click the link above to Verify!**\n\n"
                        "👇 **Now generate an API Key from Render Dashboard and send it here.**\n"
                        "_(API Key starts with rnd_...)"
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
        await message.reply_text("⚠️ **Invalid API Key!**\nIt must start with `rnd_`. Please send again.")
        return

    wait_msg = await message.reply_text("🔄 **Fetching Owner ID from Render...**")

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

            # 🔥 FINAL RESULT BLOCK (Lower Case Keys)
            final_text = (
                "✅ **ALL SET! HERE IS YOUR DATA**\n\n"
                "👇 **Click to Copy All:**\n"
                f"```\n"
                f"email={email}\n"
                f"password={password}\n"
                f"owner_id={owner_id}\n"
                f"render_api_key={api_key}\n"
                f"```\n\n"
                "👆 **Ready for deployment!**"
            )
            
            await wait_msg.edit_text(
                final_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Start New Account", callback_data="gen_mail")]
                ])
            )
            
            # Clear Session for Security
            del user_sessions[chat_id]
            
        else:
            await wait_msg.edit_text(
                f"❌ **Error Fetching Owner ID**\nStatus Code: {response.status_code}\n\nIs the API Key correct? Try again.",
                reply_markup=InlineKeyboardMarkup([
                     [InlineKeyboardButton("🔄 Retry Process", callback_data="gen_mail")]
                ])
            )

    except Exception as e:
        await wait_msg.edit_text(f"❌ **Crash:** {str(e)}")

print("🤖 HEROKU BOT STARTED!")
app.run()
