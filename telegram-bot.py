#!/usr/bin/env python3

import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
)
import requests
import json

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

API_URL = "http://127.0.0.1:5001/api"


async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [KeyboardButton("Выбрать продукт")],
        [KeyboardButton("Мои заказы")],
        [KeyboardButton("Вернуть заказ")],
    ]
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


async def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    user_id = update.message.from_user.id
    user_data = context.user_data

    try:
        # Состояния диалога
        STATE_MAIN = "main"
        STATE_PRODUCTS = "products"
        STATE_REFUND = "refund"

        # Инициализация состояния
        if 'state' not in user_data:
            user_data['state'] = STATE_MAIN

        # Обработка команды отмены
        cancel_keyboard = [[KeyboardButton("Главное меню")]]

        if text == "Главное меню":
            user_data['state'] = STATE_MAIN
            return await start(update, context)

        # Обработка по текущему состоянию
        if user_data['state'] == STATE_MAIN:
            if text == "Выбрать продукт":
                user_data['state'] = STATE_PRODUCTS
                await show_products(update, user_id)
            elif text == "Мои заказы":
                await show_orders(update, user_id)
            elif text == "Вернуть заказ":
                user_data['state'] = STATE_REFUND
                await start_refund(update, user_id)
            else:
                await update.message.reply_text(
                    "Неизвестная команда",
                    reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))

        elif user_data['state'] == STATE_PRODUCTS:
            if text in ["Product 1", "Product 2", "Product 3"]:
                await create_order(update, user_id, text)
                user_data['state'] = STATE_MAIN
            else:
                await update.message.reply_text(
                    "Некорректный выбор продукта",
                    reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))

        elif user_data['state'] == STATE_REFUND:
            if await process_refund(update, user_id, text):
                user_data['state'] = STATE_MAIN

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await update.message.reply_text(
            "Произошла ошибка. Возврат в главное меню",
            reply_markup=ReplyKeyboardMarkup(cancel_keyboard, resize_keyboard=True))
        user_data['state'] = STATE_MAIN

async def show_products(update: Update, user_id: int) -> None:
    products = ["Product 1", "Product 2", "Product 3"]
    keyboard = [[KeyboardButton(p)] for p in products]
    await update.message.reply_text(
        "Выберите продукт:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


async def create_order(update: Update, user_id: int, product: str) -> None:
    try:
        response = requests.post(
            f"{API_URL}/create_order", json={"user_id": user_id, "product": product}
        )
        if response.status_code == 201:
            order_id = response.json()["order_id"]
            keyboard = [[KeyboardButton(f"Оплатить {product}")]]
            await update.message.reply_text(
                f"Заказ {order_id} создан!",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            )
    except requests.exceptions.RequestException as e:
        await update.message.reply_text("Ошибка соединения с сервером")


async def show_orders(update: Update, user_id: int) -> None:
    try:
        response = requests.get(f"{API_URL}/orders?user_id={user_id}")
        if response.status_code == 200:
            orders = response.json()
            if orders:
                msg = "Ваши заказы:\n" + "\n".join(
                    [f"{o['id']}: {o['product']} ({o['status']})" for o in orders]
                )
                await update.message.reply_text(msg)
            else:
                await update.message.reply_text("Заказов нет")
    except requests.exceptions.RequestException:
        await update.message.reply_text("Ошибка получения заказов")


async def start_refund(update: Update, user_id: int) -> None:
    try:
        response = requests.get(f"{API_URL}/orders?user_id={user_id}")
        if response.status_code == 200:
            refundable = [o for o in response.json() if o["status"] == "paid"]
            if refundable:
                keyboard = [[KeyboardButton(f"REFUND_{o['id']}")] for o in refundable]
                await update.message.reply_text(
                    "Выберите заказ для возврата:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
                )
            else:
                await update.message.reply_text("Нет доступных заказов для возврата")
    except requests.exceptions.RequestException:
        await update.message.reply_text("Ошибка получения заказов")


async def process_refund(update: Update, user_id: int, text: str) -> None:
    order_id = text.split("_")[1]
    try:
        response = requests.post(
            f"{API_URL}/refund", json={"user_id": user_id, "order_id": order_id}
        )
        if response.status_code == 200:
            await update.message.reply_text(f"Возврат для заказа {order_id} выполнен")
            return True
        else:
            await update.message.reply_text("Ошибка возврата")
            return False
    except requests.exceptions.RequestException:
        await update.message.reply_text("Ошибка соединения с сервером")
        return False


def main() -> None:
    application = Application.builder().token(
        "7567195140:AAHAFnyTM9V5s7A5sQYiOcv5B_GLl1CF-HQ").build()

    application.add_handler(
        CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND,
                       handle_message)
    )

    application.run_polling()


if __name__ == "__main__":
    main()
