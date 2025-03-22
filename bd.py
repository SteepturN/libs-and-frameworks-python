#!/usr/bin/env python3
import sqlite3
from contextlib import closing
import os
DATABASE_NAME = os.environ["DATABASE_NAME"]


def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}


def update_subscription_success(time, payment_id):
    """Обновление подписки при успешном платеже"""
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        conn.execute('''
            UPDATE subscriptions
            SET last_payment = ?, last_error_message = NULL
            WHERE payment_method_id = ?
        ''', (time, payment_id))
        conn.commit()
def update_subscription_error(time, payment_id):
        with closing(sqlite3.connect(DATABASE_NAME)) as conn:
            conn.execute('''
                UPDATE subscriptions
                SET last_error_message = ?
                WHERE payment_method_id = ?
            ''', (time, payment_id))
            conn.commit()


def update_set_refund_status(id):
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        conn.execute(f'''
        UPDATE payments
        SET status = 'refunded'
        WHERE id = '{id}'
        ''')
        conn.commit()

def update_table(table, search_name, search_id, set_pairs):
    set_string = ", ".join([f"{l} = {r}" for (l, r) in set_pairs])
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        conn.execute(f'''
        UPDATE {table}
        SET {set_string}
        WHERE {search_name} =
        ''', (search_id,))
        conn.commit()


def payments_insert(id, chat_id, price, currency, status,
                    product, payment_method_id, is_recurrent, created_at):
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO payments
            (id, chat_id, amount, currency, status, description,
                payment_method_id, is_recurrent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (id, chat_id, price, currency, status,
              product, payment_method_id, is_recurrent, created_at
        ))
        conn.commit()

def subscriptions_insert(payment_method_id, chat_id, saved, last_payment,
                         last_error_message, started, interval, amount,
                         currency, description):
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO subscriptions
            (payment_method_id, chat_id, saved, last_payment,
            last_error_message, started, interval, amount,
            currency, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            (payment_method_id, chat_id, saved, last_payment,
             last_error_message, started, interval, amount,
             currency, description)
        ))
        conn.commit()


def get_orders(search_name, search_id, table='payments', num='all', select='*'):
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        conn.row_factory = dict_factory

        cursor = conn.cursor()

        orders = cursor.execute(
            f"select {select} from {table} where {search_name} = \"{search_id}\"")
        if num == 'all':
            orders = orders.fetchall()
        else:
            orders = orders.fetchone()
    return orders

def get_active_subscriptions():
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Получаем все активные подписки
        cursor.execute('''
            SELECT * FROM subscriptions
            WHERE saved = true AND last_error_message IS NULL
        ''')
        subscriptions = cursor.fetchall()
    return subscriptions

def get_failed_subscriptions():
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Получаем все активные подписки
        cursor.execute('''
            SELECT * FROM subscriptions
            WHERE last_error_message IS NOT NULL
        ''')
        failed_subs = cursor.fetchall()
    return failed_subs



if __name__ == '__main__':
    with closing(sqlite3.connect(DATABASE_NAME)) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS payments
                        (id TEXT PRIMARY KEY,
                        chat_id TEXT,
                        amount REAL,
                        currency TEXT,
                        status TEXT,
                        description TEXT,
                        payment_method_id TEXT,
                        is_recurrent BOOLEAN,
                        refunded BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP
                        );''')

        conn.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                        (payment_method_id TEXT PRIMARY KEY,
                        chat_id TEXT,
                        saved BOOLEAN,
                        last_payment TIMESTAMP,
                        last_error_message TIMESTAMP,
                        started TIMESTAMP,
                        interval INT,
                        amount REAL,
                        currency TEXT,
                        description TEXT
                        );''')
        # interval should be month maybe
        conn.commit()
