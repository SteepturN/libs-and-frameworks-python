#!/usr/bin/env python3

import sqlite3
import logging
from contextlib import closing
from datetime import datetime, timedelta
import threading
import time
from fastapi import FastAPI, HTTPException, status
import requests
from yookassa_api import PaymentProcessor
logger = logging.getLogger(__name__)
DATABASE_NAME = "payments.db"
CHECK_INTERVAL = 10  # 2 минуты в секундах
RETRY_DELAY = 24*60*60      # 1 день
# RETRY_DELAY = 1      # 1 минута в секундах

NOTIFICATION_API_URL = "http://127.0.0.1:5002"
# payment_processor = yookassa_api.PaymentProcessor(SHOP_ID, API_KEY, URL)


def process_recurrent_payment(subscription: dict, payment_processor: PaymentProcessor):
    """Обработка одного рекуррентного платежа"""
    try:
        # Вызов API для создания рекуррентного платежа
        order = payment_processor.create_payment(
            subscription['amount'],
            'RUB',
            subscription['description'],
            subscription['chat_id'],
            False,
            subscription['payment_method_id'],
            metadata={'payment_interval': subscription['interval'],
                      'chat_id': subscription['chat_id']})

        if not order:
            update_subscription_error(subscription, 'order cancelled')
        elif order['status'] == 'canceled':
            update_subscription_error(subscription, 'order cancelled', "failure")
        else:
            update_subscription_success(subscription)

    except Exception as e:
        logger.error(f"Payment error: {str(e)}")
        update_subscription_error(subscription['payment_method_id'])

def update_subscription_success(subscription):
    """Обновление подписки при успешном платеже"""
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        conn.execute('''
            UPDATE subscriptions
            SET last_payment = ?, last_error_message = NULL
            WHERE payment_method_id = ?
        ''', (datetime.now().isoformat(), subscription['payment_method_id']))
        conn.commit()

def update_subscription_error(subscription: dict, error_message: str = '', message_type: str = 'error'):
    """Обновление подписки при ошибке и отправка уведомления"""
    try:
        # Обновление записи в БД
        with closing(sqlite3.connect(DATABASE_NAME)) as conn:
            conn.execute('''
                UPDATE subscriptions
                SET last_error_message = ?
                WHERE payment_method_id = ?
            ''', (datetime.now().isoformat(),
                  subscription['payment_method_id']))
            conn.commit()

        # Отправка уведомления через REST API
        notification_data = {
            "chat_id": subscription['chat_id'],
            "message_type": message_type,
            "details": {
                "payment_id": subscription['payment_method_id'],
                "error": error_message,
                "amount": subscription['amount'],
                "currency": subscription['currency']
            }
        }

        requests.post(
            f"{NOTIFICATION_API_URL}/send-notification",
            json=notification_data,
            timeout=5
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send notification: {str(e)}")
    except Exception as e:
        logger.error(f"Subscription update error: {str(e)}")

def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}

def check_recurrent_payments(payment_processor):
    """Проверка и обработка рекуррентных платежей"""
    while True:
        try:
            with closing(sqlite3.connect(DATABASE_NAME)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("select count(*) from subscriptions")
                count = cursor.fetchone()[0]

                # conn.row_factory = dict_factory
                cursor.execute("select * from subscriptions")
                all_info = cursor.fetchall()

                # Получаем все активные подписки
                cursor.execute('''
                    SELECT * FROM subscriptions
                    WHERE saved = true AND last_error_message IS NULL
                ''')
                subscriptions = cursor.fetchall()

                for sub in subscriptions:
                    logger.info(dict(sub))
                    now = datetime.now()
                    last_payment = datetime.fromisoformat(sub['last_payment'])
                    next_payment = last_payment + timedelta(seconds=sub['interval'])

                    # Проверка необходимости оплаты
                    if now >= next_payment:
                        print('payment incoming')
                        process_recurrent_payment(dict(sub), payment_processor)
                    else:
                        print(f'not yet: {now} {next_payment}')
                # Проверка подписок с ошибками
                cursor.execute('''
                    SELECT * FROM subscriptions
                    WHERE last_error_message IS NOT NULL
                ''')
                failed_subs = cursor.fetchall()

                for sub in failed_subs:
                    error_time = datetime.fromisoformat(sub['last_error_message'])
                    if (datetime.now() - error_time).total_seconds() >= RETRY_DELAY:
                        process_recurrent_payment(dict(sub), payment_processor)

        except Exception as e:
            logger.error(f"Recurrent check error: {str(e)}")

        time.sleep(CHECK_INTERVAL)
        logger.info(f'interval finished: {count} subscriptions')
        # for el in all_info:
        #     logger.info(f'all: {dict(el)}')

def start_recurrent_checker(payment_processor):
    """Запуск фонового потока для проверки платежей"""
    thread = threading.Thread(
        target=check_recurrent_payments, args=[payment_processor], daemon=True)
    thread.start()
    logger.info("Recurrent payments checker started")
