# main.py – SUPER HIMOYALI VERSIYA
import os
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncpg

# ───── SOZLAMALAR ─────
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
db_pool = None

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ───── GUARDIAN HIMIYA ─────
FLOOD_LIMIT = 6          # 3 soniyada 6 ta xabar → blok
FLOOD_WINDOW = 3
BANNED_USERS = set()     # Tez cache
USER_MSG_LOG = {}        # {user_id: [timestamp, ...]}
GROUP_MODE = {}          # {chat_id: True} — faqat admin qoʻshsa ishlaydi

INVALID_CHARS = r'\/:*?"<>|'

class RenameState(StatesGroup):
    waiting_for_new_name = State()

# ───── HIMIYA FUNKSIYALARI ─────
async def is_flood(user_id: int, chat_id: int) -> bool:
    now = asyncio.get_event_loop().time()
    log = USER_MSG_LOG.get(user_id, [])
    log = [t for t in log if now - t < FLOOD_WINDOW]
    log.append(now)
    USER_MSG_LOG[user_id] = log
    return len(log) > FLOOD_LIMIT

async def block_user(user_id: int, username: str = "", chat_title=""):
    if user_id in BANNED_USERS:
        return
    BANNED_USERS.add(user_id)
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO banned (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)

    alert = (
        f"GUARDIAN: Hujum aniqlandi!\n\n"
        f"Foydalanuvchi: {username or 'NoName'} (<code>{user_id}</code>)\n"
        f"Guruh: {chat_title or 'Shaxsiy'}\n"
        f"Sabab: Flood / Spam\n"
        f"Vaqt: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"Status: BLOKLANDI"
    )
    try:
        await bot.send_message(ADMIN_ID, alert, parse_mode="HTML")
    except: pass

# ───── DB ─────
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_seen TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS banned (
                user_id BIGINT PRIMARY KEY
            );
        ''')

async def add_user(user: types.User):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, username, first_name) VALUES ($1,$2,$3)
            ON CONFLICT (user_id) DO UPDATE SET last_seen = NOW()
        ''', user.id, user.username, user.full_name)

async def is_banned(user_id: int) -> bool:
    if user_id in BANNED_USERS:
        return True
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT 1 FROM banned WHERE user_id = $1", user_id) is not None

# ───── KLAVIATURA ─────
def main_menu(is_admin=False):
    kb = [[KeyboardButton(text="Fayl nomini o'zgartirish")]]
    if is_admin:
        kb.append([KeyboardButton(text="Statistika"), KeyboardButton(text="Xabar yuborish")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ───── ASOSIY HANDLERLAR (HIMIYALI) ─────
@dp.message(Command("start"))
async def start(message: types.Message):
    user = message.from_user
    chat = message.chat

    # Guruh bo'lsa — faqat admin qoʻshsa ishlaydi
    if chat.type in ["group", "supergroup"]:
        if chat.id not in GROUP_MODE:
            admins = await bot.get_chat_administrators(chat.id)
            if user.id not in [a.user.id for a in admins]:
                return  # jim o'tib ketadi
        GROUP_MODE[chat.id] = True

    if await is_banned(user.id):
        return

    if await is_flood(user.id, chat.id):
        await block_user(user.id, user.full_name, chat.title or "")
        return await message.answer("Siz bloklandingiz.")

    await add_user(user)
    await message.answer(
        "Fayl nomini o'zgartirish botiga xush kelibsiz!\n\n"
        "Fayl yuboring → yangi nom so'rayman → tayyor!\n\n"
        "<b>Taqiqlangan belgilar:</b> \\ / : * ? \" < > |",
        reply_markup=main_menu(user.id == ADMIN_ID)
    )

# Barcha fayl va xabarlar uchun umumiy himoya
@dp.message()
async def global_handler(message: types.Message, state: FSMContext):
    user = message.from_user
    chat = message.chat

    # Bloklanganlar
    if await is_banned(user.id):
        return

    # Flood
    if await is_flood(user.id, chat.id):
        await block_user(user.id, user.full_name, chat.title or "")
        return await message.answer("Spam qilmang. Bloklandingiz.")

    # Guruhda faqat admin qoʻshsa ishlasin
    if chat.type in ["group", "supergroup"]:
        if chat.id not in GROUP_MODE:
            return

    # Endi normal handlerlarga yoʻnaltirish
    if message.text == "Fayl nomini o'zgartirish":
        return await ask_file(message)
    if message.text == "Statistika" and user.id == ADMIN_ID:
        return await stats(message)
    if message.text == "Xabar yuborish" and user.id == ADMIN_ID:
        return await broadcast_ask(message, state)

    # Fayl keldi
    if message.document or message.photo or message.video or message.audio or message.voice:
        return await receive_file(message, state)

    # Boshqa xabarlar — e'tiborsiz
    return

# Qolgan handlerlar (oldingi kod bilan bir xil, faqat himoya qoʻshildi)
# ... (oldingi kodning davomi: ask_file, receive_file, rename_file, stats, broadcast ...)

# Mana qolgan qismi (faqat kerakli joylarni qoʻshdim)
async def ask_file(message: types.Message):
    await message.answer("Fayl yuboring:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Bekor qilish")]], resize_keyboard=True))

async def receive_file(message: types.Message, state: FSMContext):
    # ... oldingi kod bilan bir xil ...
    # (oldingi javobdagi receive_file funksiyasini shu yerga qoʻying)
    pass  # toʻliq kodni joylash uchun joy qoldirdim

# Qolgan funksiyalarni oldingi javobdan nusxa oling (rename_file, stats, broadcast)

# ───── START ─────
async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    print("Bot ishga tushdi | Guardian faol")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
