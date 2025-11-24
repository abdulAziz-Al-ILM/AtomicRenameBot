import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ───── MUHIM O‘ZGARUVCHILAR ─────
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # o‘zingizning ID
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN topilmadi! Railway Settings ga qo‘shing!")

# Bot yaratish (aiogram 3.7+ uchun to‘g‘ri usul)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ───── STATE ─────
class RenameState(StatesGroup):
    waiting_name = State()

# ───── KLAVIATURA ─────
def menu(admin=False):
    kb = [[KeyboardButton(text="Fayl nomini o‘zgartirish")]]
    if admin:
        kb += [[KeyboardButton(text="Statistika"), KeyboardButton(text="Xabar yuborish")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ───── HANDLERLAR ─────
@dp.message(Command("start"))
async def start(message: types.Message):
    text = (
        "<b>Fayl nomini o‘zgartirish boti</b>\n\n"
        "Fayl yuboring → yangi nom so‘rayman → tayyor!\n\n"
        "Taqiqlangan belgilar: \\ / : * ? \" < > |"
    )
    await message.answer(text, reply_markup=menu(message.from_user.id == ADMIN_ID))

@dp.message(F.text == "Fayl nomini o‘zgartirish")
async def ask_file(message: types.Message):
    await message.answer("Fayl yuboring:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Bekor qilish")]], resize_keyboard=True))

@dp.message(F.text == "Bekor qilish")
async def cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=menu(message.from_user.id == ADMIN_ID))

@dp.message(F.document | F.photo | F.video | F.audio | F.voice)
async def got_file(message: types.Message, state: FSMContext):
    file = message.document or message.photo[-1] if message.photo else message.video or message.audio or message.voice
    file_name = getattr(file, "file_name", "fayl")
    ext = os.path.splitext(file_name)[1] or ".file"

    await state.update_data(file_id=file.file_id, ext=ext)
    await message.answer(
        f"Joriy nom: <code>{file_name}</code>\n\n"
        f"Yangi nom kiriting (faqat ism):",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Bekor qilish")]], resize_keyboard=True)
    )
    await state.set_state(RenameState.waiting_name)

@dp.message(RenameState.waiting_name)
async def rename(message: types.Message, state: FSMContext):
    if message.text == "Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=menu(message.from_user.id == ADMIN_ID))

    new_name = message.text.strip()
    if not new_name:
        return await message.answer("Nom bo‘sh bo‘lmasin!")

    if any(c in new_name for c in r'\/:*?"<>|'):
        return await message.answer("Taqiqlangan belgi ishlatdingiz!")

    data = await state.get_data()
    new_name += data["ext"]

    file = await bot.get_file(data["file_id"])
    downloaded = await bot.download_file(file.file_path)

    await bot.send_document(
        message.chat.id,
        FSInputFile(downloaded, filename=new_name),
        caption=f"{new_name}\n\nRenamed by @SizningBot"
    )
    await message.answer("Tayyor!", reply_markup=menu(message.from_user.id == ADMIN_ID))
    await state.clear()

# Admin funksiyalari (oddiy)
@dp.message(F.text == "Statistika")
async def stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer(f"Admin paneldasiz!\nUser ID: {message.from_user.id}")

@dp.message(F.text == "Xabar yuborish")
async def broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Bu yerda broadcast qilishingiz mumkin edi, lekin hozircha faqat ishlayotganini ko‘rish uchun qoldirdim :)")

# ───── START ─────
async def main():
    logging.basicConfig(level=logging.INFO)
    print("Bot ishga tushdi... Online!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
