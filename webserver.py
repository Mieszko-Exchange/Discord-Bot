# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

from discord.ext import ipc
from quart import Quart

from cogs.utils import config
from cogs.utils.logger import get_logger, prepare_logger

log = get_logger()
# prepare_logger("discord.ext.ipc.client")

server = Quart(__name__)
ipc_client = ipc.Client(secret_key=config.read("./credentials.toml")["IPC"]["secret"], port=8765)


if __name__ == "__main__":
    server.run()
