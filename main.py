# main.py – SUPER STABIL VERSIYA (o'zbekcha harflar yo'q, HTML yo'q)
import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Token va Admin
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN yo'q! Railway Settings ga qo'shing!")

# Bot yaratish (parse_mode umuman yo'q – xavfsiz!)
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class RenameState(StatesGroup):
    waiting_name = State()

# Klaviatura
def menu(admin=False):
    kb = [[KeyboardButton(text="Fayl nomini ozgartirish")]]
    if admin:
        kb += [[KeyboardButton(text="Statistika"), KeyboardButton(text="Xabar yuborish")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# START
@dp.message(Command("start"))
async def start(message: types.Message):
    text = (
        "Fayl nomini ozgartirish botiga xush kelibsiz!\n\n"
        "Fayl yuboring → yangi nom sorayman → tayyor!\n\n"
        "Eslatma: \\ / : * ? \" < > | belgilarni ishlatmang!"
    )
    await message.answer(text, reply_markup=menu(message.from_user.id == ADMIN_ID))

# Fayl so'rash
@dp.message(F.text == "Fayl nomini ozgartirish")
async def ask_file(message: types.Message):
    await message.answer("Fayl yuboring (rasm, video, hujjat...):",
                        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Bekor qilish")]], resize_keyboard=True))

# Bekor qilish
@dp.message(F.text == "Bekor qilish")
async def cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=menu(message.from_user.id == ADMIN_ID))

# Fayl keldi
@dp.message(F.document | F.photo | F.video | F.audio | F.voice)
async def got_file(message: types.Message, state: FSMContext):
    file = message.document or (message.photo[-1] if message.photo else None) or message.video or message.audio or message.voice
    if not file:
        return

    file_name = getattr(file, "file_name", "fayl")
    ext = ""
    if "." in file_name:
        ext = file_name[file_name.rfind("."):]  # .mp4, .jpg va h.k.

    await state.update_data(file_id=file.file_id, ext=ext, original=file_name)
    await message.answer(
        f"Joriy nom: {file_name}\n\n"
        f"Yangi nom kiriting (faqat ism):",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Bekor qilish")]], resize_keyboard=True)
    )
    await state.set_state(RenameState.waiting_name)

# Yangi nom kiritildi
@dp.message(RenameState.waiting_name)
async def rename(message: types.Message, state: FSMContext):
    if message.text == "Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=menu(message.from_user.id == ADMIN_ID))

    new_name = message.text.strip()
    if not new_name:
        return await message.answer("Nom bosh bolmasin!")

    if any(c in new_name for c in r'\/:*?"<>|'):
        return await message.answer("Bunday belgilar ishlatib bolmaydi!")

    data = await state.get_data()
    final_name = new_name + data["ext"]

    file_info = await bot.get_file(data["file_id"])
    downloaded = await bot.download_file(file_info.file_path)

    await bot.send_document(
        message.chat.id,
        FSInputFile(downloaded, filename=final_name),
        caption=f"{final_name}\n\nRenamed by @SizningBot"
    )
    await message.answer("Tayyor!", reply_markup=menu(message.from_user.id == ADMIN_ID))
    await state.clear()

# Admin tugmalari (hozircha oddiy javob)
@dp.message(F.text == "Statistika")
async def stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Admin paneldasiz!")

@dp.message(F.text == "Xabar yuborish")
async def broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Bu yerda broadcast qilishingiz mumkin edi :)")

# Ishga tushirish
async def main():
    print("Bot ishga tushdi va javob beradi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
