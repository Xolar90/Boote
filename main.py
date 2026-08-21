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

# ==================== الإعدادات المطلوبة ====================
MAX_REPLIES_PER_USER = 3                 # 3 ردود فقط لكل شخص
REPLY_WINDOW_SECONDS = 7200              # كل ساعتين (2 × 60 × 60)
OWNER_INACTIVITY_THRESHOLD = 60          # ثانية خمول قبل البدء بالرد

# ==================== الذاكرة ====================
# {chat_id: {"count": int, "window_start": float, "history": list}}
USER_CONVERSATIONS: Dict[int, Dict[str, Any]] = {}
LAST_OWNER_ACTIVITY: float = 0.0
OWNER_ID: int | None = None
OWNER_IDS: set[int] = set()

# ==================== الشخصية ====================
SYSTEM_PROMPT = (
    "أنت شخص عراقي واقعي ولطيف جداً تجاوب في محادثة تليجرام خاصة نيابة عن صاحب "
    "الحساب (صاحب الحساب مو يمه التلفون هسه طالع أو مشغول).\n\n"
    "قواعد إلزامية:\n"
    "1. لهجة عراقية/بغدادية عفوية وطبيعية 100% (هلا عيوني، حبيبي، شخبارك، شكو ماكو، "
    "دومك يارب، تدلل، ههههه، فدوه لعينك، لا تاكل هم).\n"
    "2. افهم السياق وجاوب بدقة ومختصر.\n"
    "3. ممنوع التحدث كبوت أو تكرار نفس الجملة.\n"
    "4. كل رد فريد وذكي ومناسب للرسالة.\n"
    "5. إذا أرسل المستخدم رابط أو لينك → قل له إن صاحب الحساب لما يرجع بيشوف الرابط اللي أرسله."
)

# ==================== كشف الروابط ====================
URL_PATTERN = re.compile(
    r"(https?://[^\s]+)|(www\.[^\s]+)|(t\.me/[^\s]+)|(telegram\.me/[^\s]+)",
    re.IGNORECASE,
)

def contains_link(text: str) -> bool:
    return bool(URL_PATTERN.search(text or ""))


# ==================== ردود احتياطية ذكية ومتنوعة ====================
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

    # رابط
    if contains_link(user_text):
        return pick([
            "تمام عيوني، لما يرجع صاحب الحساب بيشوف الرابط اللي أرسلته إن شاء الله ❤️",
            "وصل الرابط، هسه هو مو يمه الفون بس لما يرجع يشوفه تدلل",
            "حاضر، سجّلت الرابط، يرجع صاحب الحساب ويشوفه قريب إن شاء الله",
            "الرابط واصل عيوني، بيوصله لما يرجع يحاجيك 🔗",
        ])

    # تحيات
    if any(w in text for w in ["هلا", "هلو", "مرحبا", "السلام", "سلام", "هاي", "أهلا", "اهلا"]):
        return pick([
            "هلا بيك عيوني ❤️ شخبارك؟",
            "هلا والله حبيبي، شلونك؟",
            "أهلاً وسهلاً تدلل، شكو ماكو؟",
            "هلا عيوني، دومك يارب 🌹",
            "وعليكم السلام حبيبي، شلونك؟",
        ])

    # متى يرجع
    if any(w in text for w in ["شوكت", "متى", "يمتى", "يرجع", "وقت"]):
        return pick([
            "هسه هو طالع شغلة، تقريباً ساعة زمان ويرجع إن شاء الله ⏳",
            "ما يمه الفون هسه، بس يفرغ يرجعلك خبر خلال ساعة أو أقل ❤️",
            "عنده شغل برا، يرجع قريب إن شاء الله، لا تاكل هم",
            "شوي مشغول، بس يرجع يحاجيك بأقرب وقت تدلل",
        ])

    # شنو / ماذا
    if any(w in text for w in ["شنو", "ماذا", "ايش", "وشو", "قصدك"]):
        return pick([
            "ههه شنو بالضبط؟ وضحلي أكثر عيوني",
            "ما فهمت زين، عيد السؤال لو سمحت حبيبي",
            "قصدك شنو بالضبط؟ قلي أكثر تفاصيل",
        ])

    # شبيك / شلونك
    if any(w in text for w in ["شبيك", "شلك", "وينك", "شلونك", "شخبارك"]):
        return pick([
            "والله تمام الحمد لله، بس صاحب الحساب مو يمه الفون هسه ❤️",
            "زين الحمد لله، هو طالع شغلة ويرجع قريب",
            "بخير تدلل، بس هو مشغول شوي حالياً",
        ])

    # وزي / تمام
    if any(w in text for w in ["وزي", "وزين", "تمام", "اوك", "اوكي", "طيب"]):
        return pick([
            "تمام عيوني ❤️",
            "تدلل حبيبي",
            "إن شاء الله يرجع قريب ويحاجيك",
            "زين، لا تاكل هم",
        ])

    # لماذا / ليش
    if any(w in text for w in ["لماذا", "ليش", "نفس", "تكرر"]):
        return pick([
            "هههه آسف، صاحب الحساب مشغول واحنا نحاول نرد عنّه 😅",
            "لأن هو مو يمه الفون هسه، بس يرجع يحاجيك بنفسه قريب",
            "هسه الوضع شغلة، بس لا تاكل هم يرجعك خبر",
        ])

    # شكر
    if any(w in text for w in ["شكرا", "شكراً", "مشكور", "تسلم", "يعطيك"]):
        return pick([
            "تدلل عيوني ❤️",
            "تكرم حبيبي، أي وقت",
            "العفو والله، دومك يارب",
        ])

    # ضحك
    if any(w in text for w in ["ههه", "هههه", "😂", "🤣"]):
        return pick([
            "ههههه والله 😂",
            "هههه تدلل",
            "ههههه عيوني",
        ])

    # افتراضي
    return pick([
        "هسه هو مو يمه التلفون، بس يرجع يحاجيك إن شاء الله ❤️",
        "صاحب الحساب طالع شغلة، يرجع قريب تدلل",
        "ما يمه الفون هسه، بس يفرغ يرجعلك خبر ⏳",
        "عيوني هو مشغول شوي، بس يرجعك إن شاء الله لا تاكل هم",
        "شوي صبر، يرجع قريب ويحاجيك بنفسه",
    ])


# ==================== محركات الذكاء الاصطناعي ====================
async def query_gemini(messages_history: List[dict]) -> str:
    if not GEMINI_API_KEY:
        logger.warning("⚠️ GEMINI_API_KEY غير موجود")
        return ""

    contents = []
    for msg in messages_history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-1.5-pro"]

    for model in models:
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
                        logger.error(f"❌ Gemini {model} status={resp.status} | {body[:300]}")
                        if resp.status in (400, 403):
                            break
        except Exception as e:
            logger.error(f"استثناء Gemini ({model}): {e}")
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
            logger.error(f"استثناء Groq: {e}")
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
            logger.error(f"استثناء OpenRouter: {e}")
    return ""


async def generate_reply(history: List[dict], last_user_text: str) -> str:
    # إذا الرسالة تحتوي رابط → رد خاص حتى لو الـ AI شغال
    if contains_link(last_user_text):
        # نحاول AI أولاً، وإذا فشل نستخدم الرد الخاص بالروابط
        for func in (query_gemini, query_groq, query_openrouter):
            try:
                ans = await func(history)
                if ans and len(ans.strip()) > 2:
                    return ans.strip()
            except Exception:
                pass
        return get_smart_fallback(last_user_text, history)

    for func in (query_gemini, query_groq, query_openrouter):
        try:
            ans = await func(history)
            if ans and len(ans.strip()) > 2:
                return ans.strip()
        except Exception as e:
            logger.error(f"فشل AI: {e}")

    logger.warning("⚠️ كل محركات AI فشلت → رد محلي ذكي")
    return get_smart_fallback(last_user_text, history)


# ==================== تهيئة ====================
if not BOT_TOKEN:
    logger.critical("❌ BOT_TOKEN غير موجود")
    bot = None
else:
    bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()


def is_owner(user_id: int | None) -> bool:
    if user_id is None:
        return False
    if OWNER_ID and user_id == OWNER_ID:
        return True
    return user_id in OWNER_IDS


# ==================== المعالجات ====================
@dp.business_connection()
async def on_business_connection(event: BusinessConnection):
    global OWNER_ID
    OWNER_ID = event.user.id
    OWNER_IDS.add(event.user.id)
    logger.info(f"🔗 Business Connection | owner_id={OWNER_ID} | enabled={event.is_enabled}")


@dp.business_message(F.text)
async def handle_business_message(message: Message):
    global LAST_OWNER_ACTIVITY

    if not bot:
        return

    current_time = time.time()
    chat_id = message.chat.id
    text = (message.text or "").strip()
    from_user_id = message.from_user.id if message.from_user else None

    if not text:
        return

    try:
        # ========== لا ترد أبداً على رسائل صاحب الحساب ==========
        if is_owner(from_user_id):
            LAST_OWNER_ACTIVITY = current_time
            # نمسح محادثة هذا الشخص حتى لا يرد لاحقاً بالخطأ
            USER_CONVERSATIONS.pop(chat_id, None)
            logger.info(f"👤 رسالة من صاحب الحساب (id={from_user_id}) → تجاهل تام")
            return

        # ========== فترة الخمول ==========
        if (current_time - LAST_OWNER_ACTIVITY) < OWNER_INACTIVITY_THRESHOLD:
            remaining = int(OWNER_INACTIVITY_THRESHOLD - (current_time - LAST_OWNER_ACTIVITY))
            logger.info(f"⏳ صاحب الحساب نشط (متبقي {remaining} ث) → لا رد")
            return

        # ========== إدارة الحد: 3 ردود كل ساعتين ==========
        conv = USER_CONVERSATIONS.setdefault(
            chat_id,
            {"count": 0, "window_start": current_time, "history": []},
        )

        # إذا مرت ساعتين → صفّر العداد وابدأ نافذة جديدة
        if (current_time - conv["window_start"]) >= REPLY_WINDOW_SECONDS:
            conv["count"] = 0
            conv["window_start"] = current_time
            conv["history"] = []
            logger.info(f"🔄 نافذة جديدة (ساعتين) لـ {chat_id}")

        # وصل الحد الأقصى (3 ردود)
        if conv["count"] >= MAX_REPLIES_PER_USER:
            logger.info(f"🛑 وصل لـ 3 ردود خلال ساعتين → توقف عن الرد لـ {chat_id}")
            return

        # ========== بناء السياق ==========
        conv["history"].append({"role": "user", "content": text})
        if len(conv["history"]) > 10:
            conv["history"] = conv["history"][-10:]

        conv["count"] += 1

        # ========== توليد الرد ==========
        reply_text = await generate_reply(conv["history"], text)

        # منع تكرار آخر رد
        if len(conv["history"]) >= 2 and conv["history"][-1].get("role") == "assistant":
            if conv["history"][-1].get("content", "").strip() == reply_text.strip():
                reply_text = get_smart_fallback(text, conv["history"])

        conv["history"].append({"role": "assistant", "content": reply_text})

        # ========== إرسال ==========
        await bot.send_message(
            chat_id=chat_id,
            text=reply_text,
            business_connection_id=message.business_connection_id,
            reply_to_message_id=message.message_id,
        )
        logger.info(
            f"💬 رد {conv['count']}/3 → {chat_id} | {reply_text[:45]}..."
        )

    except Exception as e:
        logger.exception(f"❌ خطأ: {e}")


@dp.message(CommandStart())
async def handle_start(message: Message):
    await message.answer(
        "أهلاً بك 👋\n"
        "بوت الرد التلقائي الذكي (Telegram Business)\n\n"
        "القواعد:\n"
        "• يرد فقط على من يراسلك (مو على رسائلك أنت)\n"
        "• 3 ردود فقط لكل شخص كل ساعتين\n"
        "• إذا أرسل أحد رابط → يخبره إنك راح تشوف الرابط لما ترجع\n\n"
        "الأوامر:\n"
        "/setowner — سجّل نفسك كصاحب الحساب (مهم جداً)\n"
        "/status — حالة البوت\n"
        "/clear — تصفير الذاكرة"
    )


@dp.message(Command("status"))
async def handle_status(message: Message):
    active = len(USER_CONVERSATIONS)
    inactive = int(time.time() - LAST_OWNER_ACTIVITY) if LAST_OWNER_ACTIVITY else "—"
    owner = str(OWNER_ID) if OWNER_ID else "غير مسجل — استخدم /setowner"
    await message.answer(
        f"📊 الحالة:\n\n"
        f"• OWNER_ID: {owner}\n"
        f"• المحادثات النشطة: {active}\n"
        f"• آخر نشاط لك: قبل {inactive} ثانية\n"
        f"• Gemini: {'✅' if GEMINI_API_KEY else '❌'}\n"
        f"• حد الردود: {MAX_REPLIES_PER_USER} كل ساعتين"
    )


@dp.message(Command("clear"))
async def handle_clear(message: Message):
    count = len(USER_CONVERSATIONS)
    USER_CONVERSATIONS.clear()
    await message.answer(f"✅ تم تصفير {count} محادثة.")


@dp.message(Command("setowner"))
async def handle_setowner(message: Message):
    """مهم جداً: سجّل نفسك حتى البوت ما يرد على رسائلك"""
    global OWNER_ID
    if not message.from_user:
        return
    OWNER_ID = message.from_user.id
    OWNER_IDS.add(OWNER_ID)
    LAST_OWNER_ACTIVITY = time.time()
    await message.answer(
        f"✅ تم تسجيلك كصاحب الحساب\n"
        f"معرفك: `{OWNER_ID}`\n\n"
        f"الآن البوت **لن يرد على رسائلك أبداً**.\n"
        f"سيرد فقط على الأشخاص اللي يراسلونك."
    )
    logger.info(f"✅ OWNER_ID سُجّل يدوياً = {OWNER_ID}")


# ==================== خادم الويب ====================
async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="Telegram Business AI Bot running ✅", status=200)


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
    logger.info(f"Gemini: {'✅' if GEMINI_API_KEY else '❌'} | حد الردود: 3 كل ساعتين")
    await dp.start_polling(
        bot,
        allowed_updates=["message", "business_message", "business_connection", "edited_business_message"],
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("إيقاف")
