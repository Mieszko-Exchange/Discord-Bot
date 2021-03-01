# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

import asyncio
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import aiomysql

from .logger import get_logger

log = get_logger()


class SQL:
    def __init__(self, *args, **kwargs):
        self.loop = asyncio.get_event_loop()

        self.pool = None

        self.loop.create_task(self._generate_pool(**kwargs))
        self.loop.create_task(self._setup_tables())

    async def _generate_pool(self, **kwargs):
        self.pool = await aiomysql.create_pool(**kwargs)

    async def _setup_tables(self):
        await asyncio.sleep(1)


    async def close(self):
        await self.pool.close()
