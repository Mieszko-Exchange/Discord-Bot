# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

# Direct REST client for the Mieszko Exchange Payments API

__all__ = "ApiResponseError", "CurrencyType", "PaymentClient"

import asyncio
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from textwrap import indent
from typing import Optional

import aiohttp

from . import config
from .logger import get_logger

log = get_logger()

API_ROOT = config.read("./config.toml")["Exchange"]["api_root"]

class ApiResponseError(Exception):
    """Raised when the payments API returns an error response."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = str(message)

    def __str__(self):
        return f"{self.__class__.__name__}: HTTP {self.status}\n{textwrap.indent(self.message, '  ')}"

class CurrencyType(Enum):
    TNBCoin  = "TNBC"
    Litecoin = "LTC"
    Bitcoin  = "BTC"

@dataclass
class Route:
    method: str
    path: str
    url: str = field(init=False)

    def __post_init__(self):
        self.url = f"{API_ROOT}/{self.path}"

class PaymentClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

        self.loop = asyncio.get_event_loop()
        self.__session = None
        self.user_agent = f"RoboBroker Python/{sys.version_info.major}.{sys.version_info.minor} aiohttp/{aiohttp.__version__}"

        self.headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
        }

        self.loop.create_task(self.create_sess())

    # general tidyness
    async def create_sess(self):
        self.__session = aiohttp.ClientSession()

    async def close(self):
        if self.__session:
            await self.__session.close()

    @staticmethod
    async def parse_data(response):
        text = await response.text(encoding="utf-8")

        if response.headers.get("Content-Type") == "application/json":
            return json.loads(text)

        return text

    # here's where the magic happens
    async def request(self, route: Route, data: dict = None, **kwargs):
        method = route.method
        url = route.url

        data = data or {}

        api_key = self.api_key

        if "send_as" in kwargs:
            api_key = kwargs["send_as"]

        try:
            async with self.__session.request(method, url, params=dict(api_key=api_key), data=data, **kwargs) as response:
                log.debug(f"{method} {url} returned {response.status}")

                data = await self.parse_data(response)

                if 200 <= response.status < 300 :
                    log.debug(f"^ {method} returned {data}")

                    # TODO: response data validation

                    return data

                else:
                    log.error(f"^ {method} failed with HTTP {response.status}")
                    raise ApiResponseError(response.status, data)

        except Exception as e:
            print(f"[{type(e).__name__}]: {e}")

    # API methods

    # Payment receive
    def request_payment(self, currency: CurrencyType, amount: float, *, callback_url: str = None, **kwargs):
        payload = {
            "currency": currency.value,
            "amount": amount
        }

        if callback_url is not None:
            payload["callback"] = callback_url

        return self.request(Route("POST", "payments/receive"), payload, **kwargs)

    # Payment send
    def send_payment(self, currency: CurrencyType, address: str, amount: float, *, includes_fee: Optional[ bool ] = None, **kwargs):
        payload = {
            "currency": currency.value,
            "amount": amount,
            "receiveAddress": address
        }

        if includes_fee is not None:
            payload["includeFee"] = includes_fee

        return self.request(Route("POST", "payments/send"), payload, **kwargs)

    # Balance query
    def check_balance(self, currency: CurrencyType, **kwargs):
        payload = {
            "currency": currency.value
        }

        return self.request(Route("POST", "payments/balance"), payload, **kwargs)

    # Admin-type stuff

    # Authkey refresh
    def auth_refresh(self):
        return self.request(Route("GET", "user/auth/refresh"))
