# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

__all__ = "EscrowStatus", "EscrowAction", "EscrowActioner", "EscrowPayment", "EscrowEvent", "SavedAddress", "SQL"

import asyncio
import decimal
from collections import namedtuple
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from textwrap import dedent

import aiomysql

from .logger import get_logger, prepare_logger
from .payment_api import CurrencyType

log = get_logger()
prepare_logger("aiomysql")

# Set up proper decimal precision
d_context = decimal.getcontext()
d_context.prec = 18 # same as ETH
d_context.rounding = decimal.ROUND_HALF_UP
d_context.Emin = decimal.MIN_EMIN
d_context.Emax = decimal.MAX_EMAX

DATETIME_STR = "%Y-%m-%d %H:%M:%S"
TIMESTAMP_STR = f"{DATETIME_STR}.%f"

class EscrowStatus(Enum):
    Pending = "pending"
    Received = "paid"
    Finished = "complete"
    Failed = "failed"

class EscrowAction(Enum):
    Cancelled = "cancel"
    Released = "release"
    Aborted = "abort"

class EscrowActioner(Enum):
    Sender = "sender"
    Receiver = "receiver"
    Moderator = "moderator"

User = namedtuple("User", "id created_at locked")

EscrowPayment = namedtuple("EscrowPayment", "id currency sender receiver source_addr dest_addr status amount started_at for_message last_action_at")
EscrowEvent = namedtuple("EscrowEvent", "payment_id action actioner actioner_id action_at action_message")

SavedAddress = namedtuple("SavedAddress", "address is_public currency")

class SQL:
    def __init__(self, *args, **kwargs):
        self.loop = asyncio.get_event_loop()

        self.pool = None

        self.__pool_task = self.loop.create_task(self._generate_pool(**kwargs))

    async def _generate_pool(self, *, host, user, password, db, port=3306, **kwargs):
        self.pool = await aiomysql.create_pool(
            host=host, port=port, user=user, password=password, db=db, loop=self.loop, **kwargs
        )

        await asyncio.sleep(1)

    # async-friendly init
    async def init(self):
        if not self.__pool_task.done():
            await self.__pool_task

    @staticmethod
    def to_time_str(date_time):
        return date_time.strftime(DATETIME_STR)

    @staticmethod
    def from_time_str(stamp):
        return datetime.strptime(stamp, DATETIME_STR)

    @staticmethod
    def to_time_str_ms(date_time):
        return date_time.strftime(TIMESTAMP_STR)

    @staticmethod
    def from_time_str_ms(stamp):
        return datetime.strptime(stamp, TIMESTAMP_STR)

    async def close(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    # Query methods

    async def _execute(self, query, values=None):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                data = await cur.execute(query, values)

        return data

    # Higher-level utility methods

    async def ensure_user(self, user_id, *, create_locked=False):
        user = await self.get_user_details(user_id)

        if not user:
            created = await self.create_user(user_id, create_locked=create_locked)
            user = await self.get_user_details(user_id)

        return user

    # Currency methods

    async def get_currency_details(self, currency):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM Currency WHERE code = %s;", (currency.value,)
                )

                data = await cur.fetchall()

        return data

    # User methods

    async def get_user_details(self, user_id):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM User WHERE discordID = %s;", (user_id,)
                )

                data = await cur.fetchall()

        if data:
            (_id, timestamp, locked) = data[0]
            return User(_id, timestamp, bool(locked))

    async def create_user(self, user_id, *, create_locked=False):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                rows_changed = await cur.execute(
                    dedent("""
                        INSERT INTO `User` (discordID, createdAt, locked)
                        VALUES (%s, NOW(), %s);
                    """), (user_id, create_locked * 1)
                )

        return rows_changed == 1

    async def lock_user(self, user_id):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        UPDATE User SET locked = 1 WHERE discordID = %s
                        LIMIT 1;
                    """), user_id
                )
                rows_changed = cur.rowcount

        return rows_changed == 1

    async def unlock_user(self, user_id):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        UPDATE User SET locked = 0 WHERE discordID = %s
                        LIMIT 1;
                    """), user_id
                )
                rows_changed = cur.rowcount

        return rows_changed == 1

    # LinkedAddress methods

    async def get_address_for(self, user_id, currency):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        SELECT lA.address, lA.public, c.code FROM LinkedAddress lA, Currency c
                        WHERE lA.userID = %s AND lA.currency = c.id AND c.code = %s
                        LIMIT 1;
                    """), (user_id, currency.value)
                )
                data = await cur.fetchall()

        if data:
            (address, is_public, code) = data[0]
            return SavedAddress(address, bool(is_public), CurrencyType(code))

    async def get_all_addresses(self, user_id):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        SELECT lA.address, lA.public, c.code FROM LinkedAddress lA, Currency c
                        WHERE lA.userID = %s and lA.currency = c.id;
                    """), (user_id,)
                )
                data = await cur.fetchall()

        if data:
            results = []
            for (address, is_public, code) in data:
                results.append(SavedAddress(address, bool(is_public), CurrencyType(code)))

            return results

    async def set_address_private(self, user_id, address):
        async with self.pool.acquire() as con:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        UPDATE LinkedAddress SET public = 0
                        WHERE userID = %s AND address = %s;
                    """), (user_id, address)
                )
                rows_changed = cur.rowcount

        return rows_changed == 1

    async def set_address_public(self, user_id, address):
        async with self.pool.acquire() as con:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        UPDATE LinkedAddress SET public = 1
                        WHERE userID = %s AND address = %s;
                    """), (user_id, address)
                )
                rows_changed = cur.rowcount

        return rows_changed == 1

    async def add_address_for(self, user_id, currency, address, *, create_private=False):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        INSERT INTO LinkedAddress (userID, currency, address, public)
                        VALUES (%s, (SELECT id from Currency WHERE code = %s LIMIT 1), %s, %s);
                    """), (user_id, currency.value, address, create_private * 1)
                )

                address_id = cur.lastrowid

        return address_id

    async def delete_address_for(self, user_id, address):
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        DELETE FROM LinkedAddress
                        WHERE userID = %s AND address = %s
                        LIMIT 1;
                    """), (user_id, address)
                )
                rows_changed = cur.rowcount

        return rows_changed == 1

    # EscrowPayment methods

    async def get_payments(self, **kwargs):
        raise UnimplementedError()

    async def create_payment(self, currency, sender_id, receiver_id, src_addr, dst_addr, amount, *, reason=None):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        INSERT INTO EscrowPayment (currency, sender, receiver, sourceAddress, destAddress, status, amount, startedAt, forMessage)
                        VALUES ((SELECT id FROM Currency WHERE code = %s), %s, %s, %s, %s, 'pending', %s, %s, %s)
                    """), (currency.value, sender_id, receiver_id, src_addr, dst_addr, amount, self.to_time_str_ms(datetime.utcnow()), reason)
                )

                payment_id = cur.lastrowid

        return payment_id

    async def get_active_payment_by_participants(self, sender_id, receiver_id):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        SELECT E.*, C.code FROM EscrowPayment E, Currency C
                        WHERE E.sender = %s AND E.receiver = %s
                        AND E.status != 'complete' AND C.id = E.currency
                        LIMIT 1;
                    """), (sender_id, receiver_id)
                )
                data = await cur.fetchall()

        # Do proper data conversions so everything comes out polished
        if data:
            (_id, currency_id, sender_id, receiver_id, src_addr, dst_addr,
                status, amount, started_at, for_message, last_action_at, currency_code
            ) = data[0]
            return EscrowPayment(
                _id, CurrencyType(currency_code), sender_id, receiver_id,
                src_addr, dst_addr, EscrowStatus(status), amount,
                started_at, for_message, last_action_at if isinstance(last_action_at, datetime) else None
            )

    async def update_payment_status(self, payment_id, status):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        UPDATE EscrowPayment SET status = %s, lastActionAt = %s
                        WHERE id = %s;
                    """), (status.value, self.to_time_str_ms(datetime.utcnow()), payment_id)
                )

                rows_changed = cur.rowcount

        return rows_changed == 1

    # EscrowEvent methods

    async def get_payment_event(self, payment_id):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        SELECT * FROM EscrowEvent WHERE paymentID = %s LIMIT 1;
                    """), (payment_id,)
                )
                data = cur.fetchall()

        if data:
            (_id, action, actioner, actioner_id, action_at, action_msg) = data[0]
            return EscrowEvent(
                _id, EscrowAction(action), EscrowActioner(actioner), actioner_id, action_at, action_msg
            )

    async def create_payment_event(self, payment_id, action, actioner, actioner_id, *, message=None):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        INSERT INTO EscrowEvent (paymentID, action, actioner, actionerID, actionAt, actionMsg)
                        VALUES (%s, %s, %s, %s, %s, %s);
                    """), (payment_id, action.value, actioner.value, actioner_id, self.to_time_str_ms(datetime.utcnow()), message)
                )
                rows_changed = cur.rowcount

        return rows_changed == 1

    # just for database error logging
    async def create_error_report(self, report):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    dedent("""
                        INSERT INTO LoggedErrors (`level`, module, function, filename, lineno, message, `timestamp`)
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """),
                    (report.levelName, report.module, report.funcName, report.filename,
                        report.lineno, report.getMessage(), self.to_time_str(datetime.fromtimestamp(report.created))
                    )
                )

                report_id = cur.lastrowid

        return report_id
