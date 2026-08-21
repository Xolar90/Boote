import asyncio
import logging
import os
import random
import re
import time
import json
from typing import Dict, Any, List

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, BusinessConnection
from aiohttp import web
import aiohttp

# ==================== التسجيل ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BusinessBot")

# ==================== المتغيرات البيئية ====================
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
OPENROUTER_API_KEY = (
    os.getenv("OPENROUTER_API_KEY") or os.getenv("AI_API_KEY") or ""
).strip()
GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip()

# === أهم متغير: ضع رقم حسابك هنا في Render ===
# مثال: OWNER_TELEGRAM_ID=123456789
_OWNER_ENV = (os.getenv("OWNER_TELEGRAM_ID") or "").strip()
OWNER_ID_FROM_ENV: int | None = int(_OWNER_ENV) if _OWNER_ENV.isdigit() else None

# ==================== الإعدادات ====================
MAX_REPLIES_PER_USER = 3
REPLY_WINDOW_SECONDS = 7200              # ساعتان
OWNER_INACTIVITY_THRESHOLD = 45          # ثانية

# ==================== الذاكرة ====================
USER_CONVERSATIONS: Dict[int, Dict[str, Any]] = {}
LAST_OWNER_ACTIVITY: float = 0.0
OWNER_ID: int | None = OWNER_ID_FROM_ENV
OWNER_IDS: set[int] = set()
if OWNER_ID_FROM_ENV:
    OWNER_IDS.add(OWNER_ID_FROM_ENV)

# ==================== الشخصية ====================
SYSTEM_PROMPT = (
    "أنت شخص عراقي واقعي ولطيف جداً تجاوب في محادثة تليجرام خاصة نيابة عن صاحب "
    "الحساب (صاحب الحساب مو يمه التلفون هسه طالع أو مشغول).\n\n"
    "قواعد إلزامية:\n"
    "1. لهجة عراقية/بغدادية عفوية وطبيعية 100%.\n"
    "2. افهم السياق وجاوب بدقة ومختصر.\n"
    "3. ممنوع التحدث كبوت أو تكرار نفس الجملة.\n"
    "4. كل رد فريد وذكي.\n"
    "5. إذا أرسل المستخدم رابط → قل له إن صاحب الحساب لما يرجع بيشوف الرابط."
)

URL_PATTERN = re.compile(
    r"(https?://[^\s]+)|(www\.[^\s]+)|(t\.me/[^\s]+)|(telegram\.me/[^\s]+)",
    re.IGNORECASE,
)

def contains_link(text: str) -> bool:
    return bool(URL_PATTERN.search(text or ""))


def get_smart_fallback(user_text: str, history: List[dict] | None = None) -> str:
    text = (user_text or "").strip().lower()
    previous = set()
    if history:
        for h in history:
            if h.get("role") == "assistant":
                previous.add(h.get("content", "").strip())

    def pick(options: list[str]) -> str:
        available = [o for o in options if o not in previous]
        return random.choice(available if available else options)

    if contains_link(user_text):
        return pick([
            "تمام عيوني، لما يرجع صاحب الحساب بيشوف الرابط اللي أرسلته إن شاء الله ❤️",
            "وصل الرابط، هسه هو مو يمه الفون بس لما يرجع يشوفه تدلل",
            "حاضر، سجّلت الرابط، يرجع صاحب الحساب ويشوفه قريب إن شاء الله",
            "الرابط واصل عيوني، بيوصله لما يرجع يحاجيك 🔗",
        ])

    if any(w in text for w in ["هلا", "هلو", "مرحبا", "السلام", "سلام", "هاي", "أهلا", "اهلا"]):
        return pick([
            "هلا بيك عيوني ❤️ شخبارك؟",
            "هلا والله حبيبي، شلونك؟",
            "أهلاً وسهلاً تدلل، شكو ماكو؟",
            "هلا عيوني، دومك يارب 🌹",
        ])

    if any(w in text for w in ["شوكت", "متى", "يمتى", "يرجع", "وقت"]):
        return pick([
            "هسه هو طالع شغلة، تقريباً ساعة زمان ويرجع إن شاء الله ⏳",
            "ما يمه الفون هسه، بس يفرغ يرجعلك خبر خلال ساعة أو أقل ❤️",
            "عنده شغل برا، يرجع قريب إن شاء الله، لا تاكل هم",
            "شوي مشغول، بس يرجع يحاجيك بأقرب وقت تدلل",
        ])

    if any(w in text for w in ["شنو", "ماذا", "ايش", "وشو", "قصدك"]):
        return pick([
            "ههه شنو بالضبط؟ وضحلي أكثر عيوني",
            "ما فهمت زين، عيد السؤال لو سمحت حبيبي",
            "قصدك شنو بالضبط؟ قلي أكثر تفاصيل",
        ])

    if any(w in text for w in ["شبيك", "شلك", "وينك", "شلونك", "شخبارك"]):
        return pick([
            "والله تمام الحمد لله، بس صاحب الحساب مو يمه الفون هسه ❤️",
            "زين الحمد لله، هو طالع شغلة ويرجع قريب",
            "بخير تدلل، بس هو مشغول شوي حالياً",
        ])

    if any(w in text for w in ["وزي", "وزين", "تمام", "اوك", "اوكي", "طيب"]):
        return pick(["تمام عيوني ❤️", "تدلل حبيبي", "إن شاء الله يرجع قريب ويحاجيك", "زين، لا تاكل هم"])

    if any(w in text for w in ["لماذا", "ليش", "نفس", "تكرر"]):
        return pick([
            "هههه آسف، صاحب الحساب مشغول واحنا نحاول نرد عنّه 😅",
            "لأن هو مو يمه الفون هسه، بس يرجع يحاجيك بنفسه قريب",
            "هسه الوضع شغلة، بس لا تاكل هم يرجعك خبر",
        ])

    if any(w in text for w in ["شكرا", "شكراً", "مشكور", "تسلم", "يعطيك"]):
        return pick(["تدلل عيوني ❤️", "تكرم حبيبي، أي وقت", "العفو والله، دومك يارب"])

    if any(w in text for w in ["ههه", "هههه", "😂", "🤣"]):
        return pick(["ههههه والله 😂", "هههه تدلل", "ههههه عيوني"])

    return pick([
        "هسه هو مو يمه التلفون، بس يرجع يحاجيك إن شاء الله ❤️",
        "صاحب الحساب طالع شغلة، يرجع قريب تدلل",
        "ما يمه الفون هسه، بس يفرغ يرجعلك خبر ⏳",
        "عيوني هو مشغول شوي، بس يرجعك إن شاء الله لا تاكل هم",
        "شوي صبر، يرجع قريب ويحاجيك بنفسه",
    ])


# ==================== AI ====================
async def query_gemini(messages_history: List[dict]) -> str:
    if not GEMINI_API_KEY:
        return ""
    contents = []
    for msg in messages_history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    for model in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-1.5-pro"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "generationConfig": {"temperature": 0.95, "maxOutputTokens": 200, "topP": 0.95},
        }
        try:
            timeout = aiohttp.ClientTimeout(total=14)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    body = await resp.text()
                    if resp.status == 200:
                        data = json.loads(body)
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and "text" in parts[0]:
                                text = parts[0]["text"].strip().strip('"')
                                if text:
                                    logger.info(f"✅ Gemini ← {model}")
                                    return text
                    else:
                        logger.error(f"❌ Gemini {model} {resp.status} | {body[:250]}")
                        if resp.status in (400, 403):
                            break
        except Exception as e:
            logger.error(f"Gemini error ({model}): {e}")
    return ""


async def query_groq(messages_history: List[dict]) -> str:
    if not GROQ_API_KEY:
        return ""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + messages_history
    for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
        payload = {"model": model, "messages": msgs, "max_tokens": 180, "temperature": 0.9}
        try:
            timeout = aiohttp.ClientTimeout(total=11)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        if text:
                            logger.info(f"✅ Groq ← {model}")
                            return text
        except Exception as e:
            logger.error(f"Groq error: {e}")
    return ""


async def query_openrouter(messages_history: List[dict]) -> str:
    if not OPENROUTER_API_KEY:
        return ""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://render.com",
        "X-Title": "Iraqi Business Bot",
        "Content-Type": "application/json",
    }
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + messages_history
    for model in ["meta-llama/llama-3.3-70b-instruct:free", "google/gemini-2.0-flash-exp:free"]:
        payload = {"model": model, "messages": msgs, "max_tokens": 180, "temperature": 0.9}
        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        if text:
                            logger.info(f"✅ OpenRouter ← {model}")
                            return text
        except Exception as e:
            logger.error(f"OpenRouter error: {e}")
    return ""


async def generate_reply(history: List[dict], last_user_text: str) -> str:
    for func in (query_gemini, query_groq, query_openrouter):
        try:
            ans = await func(history)
            if ans and len(ans.strip()) > 2:
                return ans.strip()
        except Exception as e:
            logger.error(f"AI fail: {e}")
    return get_smart_fallback(last_user_text, history)


# ==================== تهيئة ====================
if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN مفقود")
    bot = None
else:
    bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()


def is_owner(user_id: int | None) -> bool:
    """التحقق القاطع: هل هذا صاحب الحساب؟"""
    if user_id is None:
        return False
    if OWNER_ID is not None and user_id == OWNER_ID:
        return True
    if user_id in OWNER_IDS:
        return True
    return False


# ==================== المعالجات ====================
@dp.business_connection()
async def on_business_connection(event: BusinessConnection):
    global OWNER_ID
    # لا نغيّر OWNER_ID إذا كان مضبوط من Environment (الأولوية له)
    if OWNER_ID_FROM_ENV:
        OWNER_IDS.add(event.user.id)
        logger.info(f"🔗 Business Connection (OWNER من ENV={OWNER_ID}) | conn_user={event.user.id}")
        return
    OWNER_ID = event.user.id
    OWNER_IDS.add(event.user.id)
    logger.info(f"🔗 Business Connection | OWNER_ID={OWNER_ID} | enabled={event.is_enabled}")


@dp.business_message()
async def handle_business_message(message: Message):
    """يعالج كل رسائل Business (نص أو غيرها)"""
    global LAST_OWNER_ACTIVITY

    if not bot:
        return

    current_time = time.time()
    chat_id = message.chat.id
    text = (message.text or message.caption or "").strip()
    from_user = message.from_user
    from_user_id = from_user.id if from_user else None

    # ========== تسجيل مفصل لمعرفة الهوية ==========
    logger.info(
        f"📩 business_message | chat={chat_id} | from_user={from_user_id} | "
        f"OWNER_ID={OWNER_ID} | text={text[:40]!r}"
    )

    # ========== 1. إذا الرسالة من صاحب الحساب → تجاهل تام ==========
    if is_owner(from_user_id):
        LAST_OWNER_ACTIVITY = current_time
        USER_CONVERSATIONS.pop(chat_id, None)
        logger.info(f"🚫 تجاهل رسالة صاحب الحساب (from={from_user_id})")
        return

    # إذا ما عندنا OWNER_ID أصلاً → خطر، نسجل تحذير
    if OWNER_ID is None and not OWNER_IDS:
        logger.warning(
            "⚠️ OWNER_ID غير معروف! البوت قد يرد على الجميع. "
            "أضف OWNER_TELEGRAM_ID في Environment أو استخدم /setowner"
        )

    if not text:
        return

    try:
        # ========== 2. فترة الخمول ==========
        if (current_time - LAST_OWNER_ACTIVITY) < OWNER_INACTIVITY_THRESHOLD:
            remaining = int(OWNER_INACTIVITY_THRESHOLD - (current_time - LAST_OWNER_ACTIVITY))
            logger.info(f"⏳ خمول غير مكتمل (متبقي {remaining}ث) → لا رد")
            return

        # ========== 3. حد 3 ردود كل ساعتين ==========
        conv = USER_CONVERSATIONS.setdefault(
            chat_id,
            {"count": 0, "window_start": current_time, "history": []},
        )

        if (current_time - conv["window_start"]) >= REPLY_WINDOW_SECONDS:
            conv["count"] = 0
            conv["window_start"] = current_time
            conv["history"] = []
            logger.info(f"🔄 نافذة جديدة لـ {chat_id}")

        if conv["count"] >= MAX_REPLIES_PER_USER:
            logger.info(f"🛑 وصل 3/3 → توقف عن {chat_id}")
            return

        # ========== 4. توليد وإرسال ==========
        conv["history"].append({"role": "user", "content": text})
        if len(conv["history"]) > 10:
            conv["history"] = conv["history"][-10:]

        conv["count"] += 1
        reply_text = await generate_reply(conv["history"], text)

        # منع تكرار آخر رد
        if len(conv["history"]) >= 2 and conv["history"][-1].get("role") == "assistant":
            if conv["history"][-1].get("content", "").strip() == reply_text.strip():
                reply_text = get_smart_fallback(text, conv["history"])

        conv["history"].append({"role": "assistant", "content": reply_text})

        await bot.send_message(
            chat_id=chat_id,
            text=reply_text,
            business_connection_id=message.business_connection_id,
            reply_to_message_id=message.message_id,
        )
        logger.info(f"💬 رد {conv['count']}/3 → chat={chat_id} | {reply_text[:40]}...")

    except Exception as e:
        logger.exception(f"❌ خطأ: {e}")


@dp.message(CommandStart())
async def handle_start(message: Message):
    owner_status = f"مسجل: {OWNER_ID}" if OWNER_ID else "غير مسجل ⚠️"
    await message.answer(
        f"أهلاً بك 👋\n\n"
        f"حالة صاحب الحساب: {owner_status}\n\n"
        f"الأوامر:\n"
        f"/setowner — سجّل نفسك كصاحب الحساب\n"
        f"/status — عرض الحالة\n"
        f"/clear — تصفير الذاكرة\n\n"
        f"أو ضع في Render:\n"
        f"OWNER_TELEGRAM_ID = رقم حسابك"
    )


@dp.message(Command("status"))
async def handle_status(message: Message):
    active = len(USER_CONVERSATIONS)
    inactive = int(time.time() - LAST_OWNER_ACTIVITY) if LAST_OWNER_ACTIVITY else "—"
    owner = str(OWNER_ID) if OWNER_ID else "غير مسجل"
    my_id = message.from_user.id if message.from_user else "?"
    await message.answer(
        f"📊 الحالة:\n\n"
        f"• OWNER_ID الحالي: {owner}\n"
        f"• معرفك أنت: {my_id}\n"
        f"• هل أنت المالك؟ {'نعم ✅' if is_owner(message.from_user.id if message.from_user else None) else 'لا'}\n"
        f"• المحادثات النشطة: {active}\n"
        f"• آخر نشاط: قبل {inactive} ثانية\n"
        f"• Gemini: {'✅' if GEMINI_API_KEY else '❌'}\n"
        f"• حد الردود: 3 كل ساعتين"
    )


@dp.message(Command("clear"))
async def handle_clear(message: Message):
    count = len(USER_CONVERSATIONS)
    USER_CONVERSATIONS.clear()
    await message.answer(f"✅ تم تصفير {count} محادثة.")


@dp.message(Command("setowner"))
async def handle_setowner(message: Message):
    global OWNER_ID
    if not message.from_user:
        return
    uid = message.from_user.id
    OWNER_ID = uid
    OWNER_IDS.add(uid)
    global LAST_OWNER_ACTIVITY
    LAST_OWNER_ACTIVITY = time.time()
    await message.answer(
        f"✅ تم تسجيلك كصاحب الحساب\n\n"
        f"معرفك: `{uid}`\n\n"
        f"الآن البوت لن يرد على رسائلك.\n\n"
        f"💡 للأمان الأفضل: ضع في Render Environment:\n"
        f"`OWNER_TELEGRAM_ID` = `{uid}`"
    )
    logger.info(f"✅ OWNER_ID سُجّل يدوياً = {uid}")


# ==================== خادم الويب ====================
async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="Business Bot OK ✅", status=200)


async def start_web_server() -> None:
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 المنفذ {port}")


async def main() -> None:
    if not bot:
        logger.critical("BOT_TOKEN مفقود")
        return
    await start_web_server()
    logger.info("🚀 البوت يعمل...")
    if OWNER_ID:
        logger.info(f"✅ OWNER_ID جاهز = {OWNER_ID}")
    else:
        logger.warning("⚠️ OWNER_ID غير مضبوط — استخدم /setowner أو OWNER_TELEGRAM_ID")
    logger.info(f"Gemini: {'✅' if GEMINI_API_KEY else '❌'} | حد: 3 ردود / ساعتين")
    await dp.start_polling(
        bot,
        allowed_updates=["message", "business_message", "business_connection", "edited_business_message"],
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("إيقاف")
