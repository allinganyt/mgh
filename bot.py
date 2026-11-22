import asyncio
import time
import aiosqlite
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
import uvicorn

BOT_TOKEN = "ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER"
WEBAPP_URL = "https://ТВОЙ_HTTPS_АДРЕС.ngrok-free.app"
ADMIN_PIN = "05061488"
COOLDOWN_SECONDS = 15
DB_PATH = "mgh_light.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

user_cooldowns: dict[int, float] = {}

def norm_user(u: str) -> str:
    return (u or "").strip().lstrip("@").lower()

class AppointmentCreate(BaseModel):
    sender_key: str
    patient_username: str
    patient_name: str
    doctor_id: int
    time_slot: str
    complaints: str = ""

class ApplicationCreate(BaseModel):
    applicant_username: str
    name: str
    role: str
    experience: str
    about: str = ""

class ToggleDoctor(BaseModel):
    pin: str
    doctor_id: int

class AddDoctor(BaseModel):
    pin: str
    name: str
    role: str
    username: str
    tg_id: int = 0

class ReviewApp(BaseModel):
    pin: str
    app_id: int
    approve: bool

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                username TEXT NOT NULL,
                tg_id INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tg_users (
                username TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_username TEXT,
                patient_name TEXT,
                doctor_id INTEGER,
                doctor_name TEXT,
                doctor_username TEXT,
                time_slot TEXT,
                complaints TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_username TEXT,
                name TEXT,
                role TEXT,
                experience TEXT,
                about TEXT
            )
        """)
        cur = await db.execute("SELECT COUNT(*) FROM doctors")
        if (await cur.fetchone())[0] == 0:
            await db.executemany(
                "INSERT INTO doctors (name, role, username, tg_id, is_active) VALUES (?, ?, ?, ?, ?)",
                [
                    ("Д-р Маркус Вэнс", "Главный хирург", "mgh_vance", 0, 1),
                    ("Д-р Елена Ростова", "Терапевт", "mgh_rostova", 0, 1),
                    ("Д-р Алекс Чен", "Травматолог", "mgh_chen", 0, 1),
                ]
            )
        await db.commit()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user and message.from_user.username:
        uname = norm_user(message.from_user.username)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO tg_users (username, chat_id) VALUES (?, ?)",
                (uname, message.chat.id)
            )
            await db.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🏥 Открыть Miami General Hospital",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    ]])
    await message.answer(
        "Добро пожаловать в **Miami General Hospital (MGH)**!\n"
        "Нажмите кнопку ниже, чтобы записаться к врачу или подать анкету на работу.\n"
        "Уведомления приходят тем, кто запустил этого бота и указал свой `@username`.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@app.get("/")
async def index():
    return FileResponse("index.html")

@app.get("/api/state")
async def get_state(sender_key: str = "guest"):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        docs = [dict(r) for r in await (await db.execute("SELECT * FROM doctors")).fetchall()]
        apps = [dict(r) for r in await (await db.execute("SELECT * FROM applications ORDER BY id DESC")).fetchall()]
        appts = [dict(r) for r in await (await db.execute("SELECT * FROM appointments ORDER BY id DESC LIMIT 30")).fetchall()]

    now = time.time()
    last = user_cooldowns.get(sender_key, 0)
    cooldown_left = max(0, int(COOLDOWN_SECONDS - (now - last)))
    return {"doctors": docs, "applications": apps, "appointments": appts, "cooldown_left": cooldown_left}

@app.post("/api/appointments")
async def create_appointment(data: AppointmentCreate):
    p_uname = norm_user(data.patient_username)
    if not p_uname:
        raise HTTPException(status_code=400, detail="Укажите ваш @username в Telegram")

    key = data.sender_key or p_uname
    now = time.time()
    last = user_cooldowns.get(key, 0)
    if now - last < COOLDOWN_SECONDS:
        left = int(COOLDOWN_SECONDS - (now - last)) + 1
        raise HTTPException(status_code=429, detail=f"Подождите {left} сек. перед следующей записью")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        doc = await (await db.execute("SELECT * FROM doctors WHERE id = ? AND is_active = 1", (data.doctor_id,))).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Врач недоступен")

        d_uname = norm_user(doc["username"])
        p_row = await (await db.execute("SELECT chat_id FROM tg_users WHERE username = ?", (p_uname,))).fetchone()
        d_row = await (await db.execute("SELECT chat_id FROM tg_users WHERE username = ?", (d_uname,))).fetchone()

        await db.execute(
            "INSERT INTO appointments (patient_username, patient_name, doctor_id, doctor_name, doctor_username, time_slot, complaints) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p_uname, data.patient_name, doc["id"], doc["name"], d_uname, data.time_slot, data.complaints)
        )
        await db.commit()

    user_cooldowns[key] = now

    patient_chat_id = p_row["chat_id"] if p_row else None
    doctor_chat_id = (d_row["chat_id"] if d_row else None) or (int(doc["tg_id"]) if doc["tg_id"] else None)

    if patient_chat_id:
        try:
            await bot.send_message(
                chat_id=patient_chat_id,
                text=(
                    f"🏥 **Miami General Hospital (MGH)**\n"
                    f"Напоминание о записи на приём:\n\n"
                    f"👨‍⚕️ **Врач:** {doc['name']} (`@{d_uname}`)\n"
                    f"🕒 **Время:** {data.time_slot}\n"
                    f"📝 **Причина:** {data.complaints or 'Плановый осмотр'}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            print("Ошибка отправки пациенту:", e)

    if doctor_chat_id:
        try:
            await bot.send_message(
                chat_id=doctor_chat_id,
                text=(
                    f"🩺 **MGH | Новый пациент записан на приём**\n\n"
                    f"👤 **Пациент:** {data.patient_name} (`@{p_uname}`)\n"
                    f"🕒 **Время:** {data.time_slot}\n"
                    f"📋 **Жалобы:** {data.complaints or 'Не указано'}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            print("Ошибка отправки врачу:", e)

    return {"ok": True, "cooldown": COOLDOWN_SECONDS}

@app.post("/api/applications")
async def create_application(data: ApplicationCreate):
    a_uname = norm_user(data.applicant_username)
    if not a_uname:
        raise HTTPException(status_code=400, detail="Укажите ваш @username")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO applications (applicant_username, name, role, experience, about) VALUES (?, ?, ?, ?, ?)",
            (a_uname, data.name, data.role, data.experience, data.about)
        )
        await db.commit()
    return {"ok": True}

@app.post("/api/admin/toggle-doctor")
async def toggle_doctor(data: ToggleDoctor):
    if data.pin != ADMIN_PIN:
        raise HTTPException(status_code=403, detail="Неверный код")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE doctors SET is_active = 1 - is_active WHERE id = ?", (data.doctor_id,))
        await db.commit()
    return {"ok": True}

@app.post("/api/admin/add-doctor")
async def add_doctor(data: AddDoctor):
    if data.pin != ADMIN_PIN:
        raise HTTPException(status_code=403, detail="Неверный код")
    u = norm_user(data.username)
    if not u:
        raise HTTPException(status_code=400, detail="Укажите @username врача")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO doctors (name, role, username, tg_id, is_active) VALUES (?, ?, ?, ?, 1)",
            (data.name, data.role, u, data.tg_id)
        )
        await db.commit()
    return {"ok": True}

@app.post("/api/admin/review-app")
async def review_app(data: ReviewApp):
    if data.pin != ADMIN_PIN:
        raise HTTPException(status_code=403, detail="Неверный код")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM applications WHERE id = ?", (data.app_id,))).fetchone()
        if row:
            u = norm_user(row["applicant_username"])
            if data.approve:
                u_row = await (await db.execute("SELECT chat_id FROM tg_users WHERE username = ?", (u,))).fetchone()
                chat_id = u_row["chat_id"] if u_row else 0
                await db.execute(
                    "INSERT INTO doctors (name, role, username, tg_id, is_active) VALUES (?, ?, ?, ?, 1)",
                    (row["name"], row["role"], u, chat_id)
                )
                if chat_id:
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"🎉 Ваша анкета в **Miami General Hospital** одобрена! Должность: **{row['role']}**.",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
            await db.execute("DELETE FROM applications WHERE id = ?", (data.app_id,))
            await db.commit()
    return {"ok": True}

async def main():
    await init_db()
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info"))
    await asyncio.gather(server.serve(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
