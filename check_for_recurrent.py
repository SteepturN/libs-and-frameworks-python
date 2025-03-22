#!/usr/bin/env python3

import logging
from contextlib import closing
from datetime import datetime, timedelta
import threading
import time
from fastapi import FastAPI, HTTPException, status
import requests
from yookassa_api import PaymentProcessor
import bd
logger = logging.getLogger(__name__)
from server_data import (
    RECURRENT_PAYMENT_CHECK_INTERVAL,
    RECURRENT_PAYMENT_RETRY_FAILED_PAYMENT_INTERVAL,
    NOTIFICATION_API_URL
)
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

        if not order or order['status'] == 'canceled':
            bd.update_subscription_error(
                datetime.now().isoformat(), subscription['payment_method_id'])
            update_subscription_error(subscription, 'order cancelled',
                                      message_type="error" if not order else "failure")
        else:
            bd.update_subscription_success(
                datetime.now().isoformat(), subscription['payment_method_id'])

    except Exception as e:
        logger.error(f"Payment error: {str(e)}")
        update_subscription_error(subscription['payment_method_id'])


def update_subscription_error(subscription: dict, error_message: str = '',
                              message_type: str = 'error'):
    """Обновление подписки при ошибке и отправка уведомления"""
    try:
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
            subscriptions = bd.get_active_subscriptions()
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
            failed_subs = bd.get_failed_subscriptions()
            for sub in failed_subs:
                error_time = datetime.fromisoformat(sub['last_error_message'])
                if (
                        (datetime.now() - error_time).total_seconds() >=
                        RECURRENT_PAYMENT_RETRY_FAILED_PAYMENT_INTERVAL
                ):
                    process_recurrent_payment(dict(sub), payment_processor)

        except Exception as e:
            logger.error(f"Recurrent check error: {str(e)}")

        time.sleep(RECURRENT_PAYMENT_CHECK_INTERVAL)

def start_recurrent_checker(payment_processor):
    """Запуск фонового потока для проверки платежей"""
    thread = threading.Thread(
        target=check_recurrent_payments, args=[payment_processor], daemon=True)
    thread.start()
    logger.info("Recurrent payments checker started")
