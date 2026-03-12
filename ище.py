import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
import logging

# ========== ТВОИ ДАННЫЕ ==========
TOKEN = "8681292995:AAEHTA2qPNw1cUtQCTzEgUVfDH_RhQzEpAQ"
ADMIN_ID = 8423212939
BOT_USERNAME = "YOUR_BOT_USERNAME"  # Вставь сюда юзернейм своего бота (без @)
# =================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Данные батла
battle = {
    "active": False,
    "round_num": 1,
    "max_rounds": 2,
    "stars": 15,
    "vote_price": 2,
    "required_channel": None,
    "round_times": [],
    "channels": [],
    "participants": {},
    "voted": set(),
    "message_ids": {},
    "next_round_task": None,
    "buy_states": {}  # {user_id: {"target_id": id, "votes": count}}
}

# ========== ПРОВЕРКА АДМИНА ==========
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# ========== ПУБЛИЧНЫЙ СТАРТ ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Главное меню в боте"""
    args = message.text.split()
    
    if len(args) > 1:
        action = args[1]
        if action == "join":
            await show_join_menu(message)
        elif action == "vote":
            await show_vote_menu(message)
        else:
            await show_main_menu(message)
    else:
        await show_main_menu(message)

async def show_main_menu(message: types.Message):
    """Показывает главное меню"""
    if not battle["active"]:
        await message.answer(
            "🏆 Батл ещё не начался!\n"
            "Следи за каналами, я сообщу когда начнём"
        )
        return
    
    text = (
        f"⚡️ Батл на {battle['stars']} ⭐️ звёзд ⚡️\n\n"
        f"🎯 Раунд {battle['round_num']}/{battle['max_rounds']}\n"
        f"👥 Участников: {len(battle['participants'])}\n"
        f"💰 1 голос = {battle['vote_price']} ⭐️\n\n"
        f"👇 Выбери действие:"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Участвовать", callback_data="menu_join"),
        InlineKeyboardButton(text="🗳 Голосовать", callback_data="menu_vote")
    )
    builder.row(
        InlineKeyboardButton(text="💎 Купить голоса", callback_data="menu_buy"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="menu_stats")
    )
    
    await message.answer(text, reply_markup=builder.as_markup())

# ========== МЕНЮ В БОТЕ ==========
@dp.callback_query(F.data.startswith("menu_"))
async def menu_handler(callback: types.CallbackQuery):
    action = callback.data.split("_")[1]
    
    if action == "join":
        await show_join_menu(callback.message)
    elif action == "vote":
        await show_vote_menu(callback.message)
    elif action == "stats":
        await show_stats(callback.message)
    elif action == "buy":
        await show_buy_menu(callback.message)
    
    await callback.answer()

async def show_join_menu(message: types.Message):
    """Меню участия в батле"""
    user_id = message.chat.id
    
    if not battle["active"]:
        await message.answer("❌ Батл не активен")
        return
    
    # Проверяем подписку
    if battle["required_channel"]:
        try:
            member = await bot.get_chat_member(battle["required_channel"], user_id)
            if member.status in ["left", "kicked"]:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{battle['required_channel'][1:]}")],
                    [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub_join")]
                ])
                await message.answer(
                    f"❌ Чтобы участвовать, подпишись на канал {battle['required_channel']}",
                    reply_markup=kb
                )
                return
        except Exception as e:
            logging.error(f"Ошибка проверки подписки: {e}")
            # Если бот не может проверить, пропускаем проверку
            pass
    
    # Проверяем, участвует ли уже
    if user_id in battle["participants"]:
        await message.answer("✅ Ты уже участвуешь в батле!")
        return
    
    # Участвуем
    name = message.chat.username or message.chat.first_name
    battle["participants"][user_id] = {
        "name": name, 
        "votes": 0, 
        "paid_votes": 0
    }
    
    await message.answer(
        "✅ Ты успешно участвуешь в батле!\n\n"
        "📢 Теперь проси друзей голосовать за тебя!\n"
        "💎 Можно купить голосы через меню бота"
    )

async def show_vote_menu(message: types.Message):
    """Меню голосования"""
    user_id = message.chat.id
    
    if not battle["active"]:
        await message.answer("❌ Батл не активен")
        return
    
    # Проверяем подписку
    if battle["required_channel"]:
        try:
            member = await bot.get_chat_member(battle["required_channel"], user_id)
            if member.status in ["left", "kicked"]:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{battle['required_channel'][1:]}")],
                    [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub_vote")]
                ])
                await message.answer(
                    f"❌ Чтобы голосовать, подпишись на канал {battle['required_channel']}",
                    reply_markup=kb
                )
                return
        except:
            pass
    
    if not battle["participants"]:
        await message.answer("❌ Пока нет участников")
        return
    
    # Показываем список участников для голосования
    text = "🗳 За кого голосуем?\n\n"
    
    sorted_ppl = sorted(battle["participants"].items(), key=lambda x: x[1]["votes"], reverse=True)
    for uid, data in sorted_ppl:
        paid_info = f" (💎 {data.get('paid_votes', 0)})" if data.get('paid_votes', 0) > 0 else ""
        text += f"👤 @{data['name']} — {data['votes']} гол.{paid_info}\n"
    
    text += f"\n💰 Бесплатный голос (1 раз в раунд)"
    
    # Создаем кнопки для бесплатного голосования
    builder = InlineKeyboardBuilder()
    row = []
    for uid, data in list(battle["participants"].items())[:5]:  # Первые 5 участников
        if uid != user_id:
            row.append(InlineKeyboardButton(text=f"🗳 @{data['name']}", callback_data=f"vote_{uid}"))
    if row:
        builder.row(*row[:2])
        if len(row) > 2:
            builder.row(*row[2:4])
        if len(row) > 4:
            builder.row(*row[4:5])
    
    # Кнопка для покупки
    builder.row(InlineKeyboardButton(text="💎 Купить платные голоса", callback_data="menu_buy"))
    
    await message.answer(text, reply_markup=builder.as_markup())

async def show_buy_menu(message: types.Message):
    """Меню покупки голосов"""
    user_id = message.chat.id
    
    if not battle["participants"]:
        await message.answer("❌ Пока нет участников")
        return
    
    # Проверяем подписку для покупки
    if battle["required_channel"]:
        try:
            member = await bot.get_chat_member(battle["required_channel"], user_id)
            if member.status in ["left", "kicked"]:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Подписаться", url=f"https://t.me/{battle['required_channel'][1:]}")],
                    [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub_buy")]
                ])
                await message.answer(
                    f"❌ Чтобы покупать голоса, подпишись на канал {battle['required_channel']}",
                    reply_markup=kb
                )
                return
        except:
            pass
    
    text = (
        f"💎 Покупка голосов\n\n"
        f"💰 1 голос = {battle['vote_price']} ⭐️\n\n"
        f"За кого хочешь купить голоса?"
    )
    
    # Кнопки с участниками для покупки
    builder = InlineKeyboardBuilder()
    for uid, data in battle["participants"].items():
        if uid != user_id:  # Не показываем кнопку для себя (нельзя купить голоса себе?)
            builder.button(text=f"@{data['name']}", callback_data=f"buy_select_{uid}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu_vote"))
    
    await message.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("buy_select_"))
async def buy_select_handler(callback: types.CallbackQuery):
    """Выбор количества голосов для покупки"""
    user_id = callback.from_user.id
    target_id = int(callback.data.split("_")[2])
    
    # Сохраняем цель в состояние
    battle["buy_states"][user_id] = {"target_id": target_id}
    
    text = (
        f"💎 Сколько голосов купить для @{battle['participants'][target_id]['name']}?\n\n"
        f"💰 Цена: {battle['vote_price']} ⭐️ за голос\n\n"
        f"Выбери количество:"
    )
    
    builder = InlineKeyboardBuilder()
    for count in [1, 3, 5, 10, 15, 20]:
        total = count * battle['vote_price']
        builder.button(text=f"{count} гол. = {total} ⭐️", callback_data=f"buy_count_{count}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu_buy"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_count_"))
async def buy_count_handler(callback: types.CallbackQuery):
    """Подтверждение покупки и создание инвойса"""
    user_id = callback.from_user.id
    votes_count = int(callback.data.split("_")[2])
    
    if user_id not in battle["buy_states"]:
        await callback.answer("❌ Ошибка, начни заново", show_alert=True)
        return
    
    target_id = battle["buy_states"][user_id]["target_id"]
    target_name = battle["participants"][target_id]["name"]
    
    # Создаем счет на оплату
    prices = [LabeledPrice(label="Голос", amount=votes_count * battle["vote_price"] * 100)]
    
    await bot.send_invoice(
        chat_id=user_id,
        title="Покупка голосов",
        description=f"{votes_count} голосов для @{target_name}",
        payload=f"vote_{target_id}_{votes_count}_{user_id}",
        provider_token="",  # Пусто для Telegram Stars
        currency="XTR",  # Telegram Stars
        prices=prices,
        start_parameter="buy_votes",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Оплатить звездами", pay=True)]
        ])
    )
    
    # Очищаем состояние
    del battle["buy_states"][user_id]
    await callback.answer()

async def show_stats(message: types.Message):
    """Показывает статистику"""
    if not battle["participants"]:
        await message.answer("📊 Пока нет участников")
        return
    
    text = f"📊 Статистика раунда {battle['round_num']}\n\n"
    
    sorted_ppl = sorted(battle["participants"].items(), key=lambda x: x[1]["votes"], reverse=True)
    for i, (uid, data) in enumerate(sorted_ppl, 1):
        crown = "👑 " if i == 1 else ""
        paid_info = f" (💎 {data.get('paid_votes', 0)})" if data.get('paid_votes', 0) > 0 else ""
        text += f"{crown}{i}. @{data['name']} — {data['votes']} гол.{paid_info}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="menu_stats"),
         InlineKeyboardButton(text="🗳 Голосовать", callback_data="menu_vote")]
    ])
    
    await message.answer(text, reply_markup=kb)

# ========== ПРОВЕРКА ПОДПИСКИ ==========
@dp.callback_query(F.data.startswith("check_sub_"))
async def check_subscription(callback: types.CallbackQuery):
    action = callback.data.split("_")[2]  # join, vote или buy
    user_id = callback.from_user.id
    
    if not battle["required_channel"]:
        await callback.answer("❌ Канал не настроен")
        return
    
    try:
        member = await bot.get_chat_member(battle["required_channel"], user_id)
        if member.status in ["left", "kicked"]:
            await callback.answer("❌ Ты всё ещё не подписан!", show_alert=True)
        else:
            await callback.answer("✅ Подписка подтверждена!")
            if action == "join":
                await show_join_menu(callback.message)
            elif action == "vote":
                await show_vote_menu(callback.message)
            elif action == "buy":
                await show_buy_menu(callback.message)
    except Exception as e:
        await callback.answer(f"❌ Ошибка проверки", show_alert=True)

# ========== БЕСПЛАТНОЕ ГОЛОСОВАНИЕ ==========
@dp.callback_query(F.data.startswith("vote_"))
async def vote_callback(callback: types.CallbackQuery):
    voter_id = callback.from_user.id
    target_id = int(callback.data.split("_")[1])
    
    if not battle["active"]:
        await callback.answer("❌ Батл не активен!", show_alert=True)
        return
    
    if voter_id == target_id:
        await callback.answer("❌ За себя голосовать нельзя!", show_alert=True)
        return
    
    if voter_id in battle["voted"]:
        await callback.answer("❌ Ты уже использовал бесплатный голос в этом раунде!\nКупи платные голоса через меню", show_alert=True)
        return
    
    if target_id not in battle["participants"]:
        await callback.answer("❌ Участник не найден!", show_alert=True)
        return
    
    # Начисляем бесплатный голос
    battle["participants"][target_id]["votes"] += 1
    battle["voted"].add(voter_id)
    
    await callback.answer("✅ Бесплатный голос учтён!")
    await show_stats(callback.message)

# ========== ПЛАТЕЖИ ==========
@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    """Подтверждение платежа"""
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    """Успешная оплата"""
    payload = message.successful_payment.invoice_payload
    parts = payload.split('_')
    
    if parts[0] == "vote":
        target_id = int(parts[1])
        votes_count = int(parts[2])
        buyer_id = int(parts[3])
        
        if target_id in battle["participants"]:
            # Начисляем платные голоса
            battle["participants"][target_id]["votes"] += votes_count
            if "paid_votes" not in battle["participants"][target_id]:
                battle["participants"][target_id]["paid_votes"] = 0
            battle["participants"][target_id]["paid_votes"] += votes_count
            
            await message.answer(
                f"✅ Оплачено {votes_count} голосов за @{battle['participants'][target_id]['name']}\n"
                f"💰 Сумма: {votes_count * battle['vote_price']} ⭐️\n\n"
                f"Теперь у @{battle['participants'][target_id]['name']} {battle['participants'][target_id]['votes']} голосов!"
            )
            
            # Обновляем статистику
            await show_stats(message)
        else:
            await message.answer("❌ Участник больше не в батле")

# ========== АДМИН ПАНЕЛЬ ==========
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет доступа")
        return
    
    await show_admin_panel(message)

async def show_admin_panel(message: types.Message):
    """Показывает админ панель"""
    status = "🔴 АКТИВЕН" if battle["active"] else "⚫ НЕ АКТИВЕН"
    
    times_text = ""
    if battle["round_times"]:
        times_text = "\n"
        for i, t in enumerate(battle["round_times"]):
            times_text += f"  • Раунд {i+1}: {t.strftime('%d.%m %H:%M')}\n"
    
    channels_text = ""
    if battle["channels"]:
        channels_text = f"\n📢 Каналы ({len(battle['channels'])}):"
        for ch in battle["channels"][:3]:
            channels_text += f"\n  • {ch['title']}"
        if len(battle["channels"]) > 3:
            channels_text += f"\n  ... и ещё {len(battle['channels'])-3}"
    else:
        channels_text = "\n❌ Нет каналов"
    
    text = (
        f"⚙️ АДМИН ПАНЕЛЬ\n\n"
        f"📊 Статус: {status}\n"
        f"💰 Приз: {battle['stars']} ⭐️\n"
        f"💎 Цена голоса: {battle['vote_price']} ⭐️\n"
        f"📈 Раунд: {battle['round_num']}/{battle['max_rounds']}\n"
        f"👥 Участников: {len(battle['participants'])}\n"
        f"📌 Канал подписки: {battle['required_channel'] or 'не установлен'}"
        f"{channels_text}"
        f"\n⏱ Времена:{times_text}"
    )
    
    builder = InlineKeyboardBuilder()
    
    if not battle["active"]:
        builder.row(InlineKeyboardButton(text="🚀 НАЧАТЬ БАТЛ", callback_data="admin_start"))
    
    builder.row(
        InlineKeyboardButton(text=f"💰 {battle['stars']}", callback_data="admin_stars"),
        InlineKeyboardButton(text=f"💎 {battle['vote_price']}", callback_data="admin_price"),
        InlineKeyboardButton(text="⏱ ВРЕМЕНА", callback_data="admin_times")
    )
    
    builder.row(
        InlineKeyboardButton(text="📢 КАНАЛЫ", callback_data="admin_channels"),
        InlineKeyboardButton(text="📌 ПОДПИСКА", callback_data="admin_channel")
    )
    
    if battle["active"]:
        builder.row(
            InlineKeyboardButton(text="⏭ СЛЕД.РАУНД", callback_data="admin_next"),
            InlineKeyboardButton(text="⏹ ЗАКОНЧИТЬ", callback_data="admin_end")
        )
    
    builder.row(InlineKeyboardButton(text="🔄 ОБНОВИТЬ", callback_data="admin_refresh"))
    
    await message.answer(text, reply_markup=builder.as_markup())

# ========== АДМИН КНОПКИ ==========
@dp.callback_query(F.data.startswith("admin_"))
async def admin_buttons_handler(callback: types.CallbackQuery):
    """Обработчик всех админских кнопок"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    action = callback.data.split("_")[1]
    
    if action == "refresh":
        await show_admin_panel(callback.message)
        await callback.answer("✅ Обновлено")
    
    elif action == "start":
        await admin_start(callback)
    
    elif action == "next":
        await admin_next(callback)
    
    elif action == "end":
        await admin_end(callback)
    
    elif action == "stars":
        await show_stars_menu(callback)
    
    elif action == "price":
        await show_price_menu(callback)
    
    elif action == "times":
        await show_times_info(callback)
    
    elif action == "channels":
        await show_channels_list(callback)
    
    elif action == "channel":
        await show_channel_info(callback)
    
    else:
        await callback.answer("❌ Неизвестная команда")

async def show_stars_menu(callback: types.CallbackQuery):
    """Меню выбора приза"""
    builder = InlineKeyboardBuilder()
    for stars in [10, 15, 20, 25, 30, 50, 100]:
        builder.button(text=f"{stars} ⭐️", callback_data=f"set_stars_{stars}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="◀️ НАЗАД", callback_data="admin_back"))
    
    await callback.message.edit_text("💰 Выбери приз за победу:", reply_markup=builder.as_markup())
    await callback.answer()

async def show_price_menu(callback: types.CallbackQuery):
    """Меню выбора цены голоса"""
    builder = InlineKeyboardBuilder()
    for price in [1, 2, 3, 5, 10]:
        builder.button(text=f"{price} ⭐️", callback_data=f"set_price_{price}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="◀️ НАЗАД", callback_data="admin_back"))
    
    await callback.message.edit_text("💎 Выбери цену одного голоса:", reply_markup=builder.as_markup())
    await callback.answer()

async def show_times_info(callback: types.CallbackQuery):
    """Показывает информацию о временах"""
    if not battle["round_times"]:
        text = "⏱ Времена не установлены\n\nИспользуй команду:\n/settimes 20:00,21:00,22:00"
    else:
        text = "⏱ Установленные времена:\n\n"
        for i, t in enumerate(battle["round_times"]):
            text += f"Раунд {i+1}: {t.strftime('%d.%m %H:%M')}\n"
        text += "\nЧтобы изменить, используй:\n/settimes 20:00,21:00,22:00"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

async def show_channels_list(callback: types.CallbackQuery):
    """Показывает список каналов"""
    if not battle["channels"]:
        text = "📢 Нет добавленных каналов\n\nДобавь меня в канал как администратора - я сам напишу тебе!"
    else:
        text = "📢 Список каналов:\n\n"
        for ch in battle["channels"]:
            text += f"• {ch['title']}\n"
            if ch.get('username'):
                text += f"  https://t.me/{ch['username']}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

async def show_channel_info(callback: types.CallbackQuery):
    """Показывает информацию о канале подписки"""
    text = f"📌 Канал для обязательной подписки:\n\n{battle['required_channel'] or 'не установлен'}\n\nИспользуй /setchannel @канал чтобы установить"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ НАЗАД", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    """Возврат в админ панель"""
    if not is_admin(callback.from_user.id):
        return
    await show_admin_panel(callback.message)
    await callback.answer()

# ========== УСТАНОВКА ЗНАЧЕНИЙ ==========
@dp.callback_query(F.data.startswith("set_stars_"))
async def set_stars_value(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    stars = int(callback.data.split("_")[2])
    battle["stars"] = stars
    await callback.answer(f"✅ Приз: {stars} ⭐️")
    await show_admin_panel(callback.message)

@dp.callback_query(F.data.startswith("set_price_"))
async def set_price_value(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    price = int(callback.data.split("_")[2])
    battle["vote_price"] = price
    await callback.answer(f"✅ Цена голоса: {price} ⭐️")
    await show_admin_panel(callback.message)

# ========== ЗАПУСК БАТЛА ==========
async def admin_start(callback: types.CallbackQuery):
    if not battle["required_channel"]:
        await callback.answer("❌ Установи канал подписки (/setchannel)", show_alert=True)
        return
    
    if not battle["round_times"]:
        await callback.answer("❌ Установи времена раундов (/settimes)", show_alert=True)
        return
    
    if not battle["channels"]:
        await callback.answer("❌ Нет каналов! Добавь меня в каналы админом", show_alert=True)
        return
    
    battle["active"] = True
    battle["participants"] = {}
    battle["voted"] = set()
    battle["round_num"] = 1
    battle["round_end_time"] = battle["round_times"][0]
    
    await schedule_round_end()
    
    bot_join_link = f"https://t.me/{BOT_USERNAME}?start=join"
    bot_vote_link = f"https://t.me/{BOT_USERNAME}?start=vote"
    
    msg = (
        f"⚡️ БАТЛ НА {battle['stars']} ⭐️ ЗВЁЗД ⚡️\n\n"
        f"🎯 Раунд 1/{battle['max_rounds']}\n"
        f"⏳ Конец: {battle['round_times'][0].strftime('%d.%m %H:%M')}\n"
        f"💰 1 голос = {battle['vote_price']} ⭐️\n\n"
        f"👇 Выбери действие в боте:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Участвовать", url=bot_join_link)],
        [InlineKeyboardButton(text="🗳 Голосовать / Купить", url=bot_vote_link)]
    ])
    
    sent_count = 0
    battle["message_ids"] = {}
    
    for channel in battle["channels"]:
        try:
            sent = await bot.send_message(channel["id"], msg, reply_markup=kb)
            battle["message_ids"][channel["id"]] = sent.message_id
            sent_count += 1
        except Exception as e:
            logging.error(f"Ошибка отправки в канал {channel['title']}: {e}")
    
    await callback.message.edit_text(f"✅ Батл запущен! Отправлено в {sent_count} каналов")
    await callback.answer()

async def admin_next(callback: types.CallbackQuery):
    await callback.answer("🔄 Запускаю следующий раунд...")
    await next_round()

async def admin_end(callback: types.CallbackQuery):
    if battle["next_round_task"]:
        battle["next_round_task"].cancel()
    
    battle["active"] = False
    
    for channel_id in battle["message_ids"].keys():
        try:
            await bot.send_message(channel_id, "❌ Батл досрочно завершен")
        except:
            pass
    
    await callback.message.edit_text("❌ Батл завершен!")
    await callback.answer()

# ========== ОСТАЛЬНЫЕ АДМИН КОМАНДЫ ==========
@dp.message(Command("setchannel"))
async def cmd_setchannel(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Используй: /setchannel @канал")
        return
    
    channel = args[1]
    if not channel.startswith('@'):
        channel = '@' + channel
    
    battle["required_channel"] = channel
    await message.answer(f"✅ Канал подписки: {channel}")

@dp.message(Command("settimes"))
async def cmd_settimes(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Используй: /settimes 20:00,21:00,22:00")
        return
    
    time_strings = args[1].split(',')
    times = []
    now = datetime.now()
    
    for i, time_str in enumerate(time_strings):
        try:
            hour, minute = map(int, time_str.strip().split(':'))
            round_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if round_time <= now and i == 0:
                round_time += timedelta(days=1)
            elif i > 0 and round_time <= times[i-1]:
                round_time += timedelta(days=1)
            
            times.append(round_time)
        except:
            await message.answer(f"❌ Ошибка: {time_str}")
            return
    
    battle["round_times"] = times
    battle["max_rounds"] = len(times)
    
    time_text = "\n".join([f"• Раунд {i+1}: {t.strftime('%d.%m %H:%M')}" for i, t in enumerate(times)])
    await message.answer(f"✅ Установлено {len(times)} раундов:\n{time_text}")

# ========== ТАЙМЕРЫ РАУНДОВ ==========
async def schedule_round_end():
    if not battle["round_end_time"] or not battle["active"]:
        return
    
    if battle["next_round_task"]:
        battle["next_round_task"].cancel()
    
    now = datetime.now()
    wait_seconds = (battle["round_end_time"] - now).total_seconds()
    
    if wait_seconds < 0:
        wait_seconds = 10
    
    battle["next_round_task"] = asyncio.create_task(round_timer(wait_seconds))

async def round_timer(seconds):
    await asyncio.sleep(seconds)
    if battle["active"]:
        await next_round()

async def next_round():
    if not battle["participants"]:
        battle["active"] = False
        for channel_id in battle["message_ids"].keys():
            try:
                await bot.send_message(channel_id, "❌ Батл завершен - нет участников")
            except:
                pass
        return
    
    sorted_ppl = sorted(battle["participants"].items(), key=lambda x: x[1]["votes"], reverse=True)
    winner_id, winner_data = sorted_ppl[0]
    
    text = f"🏆 Результаты раунда {battle['round_num']} 🏆\n\n"
    for uid, data in sorted_ppl:
        crown = "👑 " if uid == winner_id else ""
        paid_info = f" (💎 {data.get('paid_votes', 0)})" if data.get('paid_votes', 0) > 0 else ""
        text += f"{crown}@{data['name']} — {data['votes']} гол.{paid_info}\n"
    
    if battle["round_num"] >= battle["max_rounds"]:
        text += f"\n🥇 Победитель: @{winner_data['name']}\n"
        text += f"🎁 Выигрыш: {battle['stars']} ⭐️"
        battle["active"] = False
        
        for channel_id in battle["message_ids"].keys():
            try:
                await bot.send_message(channel_id, text)
            except:
                pass
    else:
        battle["round_num"] += 1
        battle["voted"] = set()
        battle["round_end_time"] = battle["round_times"][battle["round_num"] - 1]
        
        for uid in battle["participants"]:
            battle["participants"][uid]["votes"] = 0
            battle["participants"][uid]["paid_votes"] = 0
        
        for channel_id in battle["message_ids"].keys():
            try:
                await bot.send_message(channel_id, text)
            except:
                pass
        
        await schedule_round_end()
        
        bot_join_link = f"https://t.me/{BOT_USERNAME}?start=join"
        bot_vote_link = f"https://t.me/{BOT_USERNAME}?start=vote"
        
        msg = (
            f"⚡️ РАУНД {battle['round_num']} НАЧАЛСЯ! ⚡️\n\n"
            f"🎯 Раунд {battle['round_num']}/{battle['max_rounds']}\n"
            f"⏳ Конец: {battle['round_end_time'].strftime('%d.%m %H:%M')}\n"
            f"💰 1 голос = {battle['vote_price']} ⭐️\n\n"
            f"👇 Выбери действие в боте:"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Участвовать", url=bot_join_link)],
            [InlineKeyboardButton(text="🗳 Голосовать / Купить", url=bot_vote_link)]
        ])
        
        for channel in battle["channels"]:
            try:
                await bot.send_message(channel["id"], msg, reply_markup=kb)
            except:
                pass

# ========== ДОБАВЛЕНИЕ В КАНАЛЫ ==========
@dp.my_chat_member()
async def chat_member_update(update: types.ChatMemberUpdated):
    if update.from_user.id != ADMIN_ID:
        return
    
    if update.chat.type not in ["channel", "supergroup"]:
        return
    
    new_status = update.new_chat_member.status
    
    if new_status in ["administrator", "creator"]:
        exists = False
        for ch in battle["channels"]:
            if ch["id"] == update.chat.id:
                exists = True
                break
        
        if not exists:
            channel_info = {
                "id": update.chat.id,
                "title": update.chat.title,
                "username": update.chat.username
            }
            battle["channels"].append(channel_info)
            await bot.send_message(ADMIN_ID, f"✅ Добавлен канал: {update.chat.title}")
    
    elif new_status == "left":
        battle["channels"] = [ch for ch in battle["channels"] if ch["id"] != update.chat.id]
        await bot.send_message(ADMIN_ID, f"❌ Удален канал: {update.chat.title}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
