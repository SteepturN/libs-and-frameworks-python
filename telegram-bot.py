#!/usr/bin/env python3

import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CopyTextButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler
)
import requests
import json

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

API_URL = "http://127.0.0.1:5001/api"

# Состояния диалога
STATE_MAIN = "main"
STATE_PRODUCTS = "products"
STATE_REFUND = "refund"
def get_products():
    return ["Product 1", "Product 2", "Product 3"]

# Обработка команды отмены
cancel_keyboard = [[KeyboardButton("Главное меню")]]

async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [KeyboardButton("Выбрать продукт")],
        [KeyboardButton("Мои заказы")],
        [KeyboardButton("Вернуть заказ")],
    ]
    await update.effective_user.send_message(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, resize_keyboard=False, one_time_keyboard=True),
    )
    context.user_data['state'] = STATE_MAIN

async def main_state_handler(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    user_id = update.message.from_user.id
    user_data = context.user_data

    if text == "Выбрать продукт":
        user_data['state'] = STATE_PRODUCTS
        res = await show_products(update, user_id)
    elif text == "Мои заказы":
        res = await show_orders(update, user_id)
    elif text == "Вернуть заказ":
        user_data['state'] = STATE_REFUND
        res = await start_refund(update, user_id)
    else:
        await update.message.reply_text(
            "Неизвестная команда",
            reply_markup=ReplyKeyboardMarkup(
                cancel_keyboard, resize_keyboard=False, one_time_keyboard=True))
        res = False
    if not res:
        return await start(update, context)


async def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    user_id = update.message.from_user.id
    user_data = context.user_data

    try:
        # Инициализация состояния
        if 'state' not in user_data:
            user_data['state'] = STATE_MAIN

        if text == "Главное меню":
            user_data['state'] = STATE_MAIN
            return await start(update, context)

        # Обработка по текущему состоянию
        if user_data['state'] == STATE_MAIN:
            return await main_state_handler(update, context)
        elif user_data['state'] == STATE_PRODUCTS:
            if text not in get_products():
                await update.message.reply_text(
                    "Некорректный выбор продукта",
                    reply_markup=ReplyKeyboardMarkup(
                        cancel_keyboard, resize_keyboard=True))
                return await start(update, context)
            user_data['product'] = text
            return await get_confirmation(update, text)


        elif user_data['state'] == STATE_REFUND:
            if await process_refund(update, user_id, text):
                return await start(update, context)

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await update.message.reply_text(
            f"Произошла ошибка {e}. Возврат в главное меню",
            reply_markup=ReplyKeyboardMarkup(
                cancel_keyboard, resize_keyboard=False, one_time_keyboard=True))
        return await start(update, context)


async def get_confirmation(update: Update, product) -> bool:
    keyboard = [[InlineKeyboardButton("Yes", callback_data={'type': "buy"}),
                 InlineKeyboardButton("No", callback_data={'type': "start"})]]
    await update.message.reply_text(
        f"Вы хотите приобрести продукт {product}?",
        reply_markup=InlineKeyboardMarkup(
            keyboard),
    )
    return True


async def show_products(update: Update, user_id: int) -> bool:
    keyboard = [[KeyboardButton(p)] for p in get_products()]
    await update.message.reply_text(
        "Выберите продукт:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True,
                                         one_time_keyboard=True),
    )
    return True


async def handle_callback(update: Update, context: CallbackContext) -> None:
    option = update.callback_query.data
    user_id = update.callback_query.from_user.id
    product = context.user_data.get('product', None)
    order_id = context.user_data.get('order_id', None)
    query = update.callback_query
    if option['type'] == "buy" and product is not None:
        query.answer("creating order...")
        if order_id := await create_order(update, user_id, product):
            await update.effective_user.send_message(
                f"Заказ {order_id} создан!",
            )
        else:
            await update.effective_user.send_message(
                f"Заказ не создан",
            )
        context.user_data['product'] = None
    elif option['type'] == "refund":
        await process_refund(update, user_id, option['order_id'])
    elif option == "start":
        query.answer("to the start it is")

    await start(update, context)


async def create_order(update: Update, user_id: int, product: str) -> bool:
    try:
        response = requests.post(
            f"{API_URL}/create_order", json={"user_id": user_id, "product": product}
        )
        
        if response.status_code == 200:
            return response.json()["order_id"]

    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Ошибка соединения с сервером {e}")
    return False

async def show_orders(update: Update, user_id: int) -> bool:
    try:
        response = requests.get(f"{API_URL}/orders?user_id={user_id}")
        if response.status_code != 200:
            await update.message.reply_text(
                "Заказов нет")
            return False

        orders = response.json()
        if not orders:
            await update.message.reply_text(
                "response вернул пустые данные")
            return False

        await update.message.reply_text("Ваши заказы:")
        for order in orders:
            msg = (
                f"time: {order['time']}\nid: {order['id']}:\nproduct: " +
                f"{order['product']}\nstatus: ({order['status']})"
            )
            button = [
                [InlineKeyboardButton(
                    text=f"copy id",
                    copy_text=CopyTextButton(order['id']))],
                [InlineKeyboardButton(
                    text=f"REFUND",
                    callback_data={'type': "refund", 'order_id': order['id']})]
            ]
            await update.message.reply_text(
                msg, reply_markup=InlineKeyboardMarkup(button))
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Ошибка получения заказов {e}")
    return False


async def start_refund(update: Update, user_id: int) -> bool:
    try:
        response = requests.get(f"{API_URL}/orders?user_id={user_id}")
        if response.status_code == 200:
            refundable = [o for o in response.json() if o["status"] == "paid"]
            if refundable:
                keyboard = [[KeyboardButton(f"{o['id']}")] for o in refundable]
                await update.message.reply_text(
                    "Выберите заказ для возврата:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
                )
                return True
            else:
                await update.message.reply_text("Нет доступных заказов для возврата")
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Ошибка получения заказов {e}")
    return False

async def process_refund(update: Update, user_id: int, order_id: str) -> bool:
    try:
        response = requests.post(
            f"{API_URL}/refund", json={"user_id": user_id, "order_id": order_id}
        )
        if response.status_code == 200:
            await update.effective_user.send_message(f"Возврат для заказа {order_id} выполнен")
            return True
        else:
            await update.effective_user.send_message("Ошибка возврата")
    except requests.exceptions.RequestException as e:
        await update.effective_user.send_message(f"Ошибка соединения с сервером {e}")
    return False


def main() -> None:
    application = (
        Application.builder()
        .token("7567195140:AAHAFnyTM9V5s7A5sQYiOcv5B_GLl1CF-HQ")
        .arbitrary_callback_data(True)
        .build()
    )
    application.add_handler(
        CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND,
                       handle_message)
    )
    application.add_handler(
        CallbackQueryHandler(handle_callback)
    )
    application.run_polling()


if __name__ == "__main__":
    main()
