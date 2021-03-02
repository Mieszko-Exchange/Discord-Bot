# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

__all__ = "get_logger", "set_level", "set_database"

import asyncio
import inspect
import logging
import os
import sys
from datetime import datetime
from logging import Handler, handlers

# Make sure the log directory exists (and create it if not)
if not os.path.exists("logs"):
    os.makedirs("logs")

_DEBUG = any(arg.lower() == "debug" for arg in sys.argv)

LOG_LEVEL = logging.DEBUG if _DEBUG else logging.INFO


class DatabaseErrorHandler(Handler):
    def __init__(self, db):
        self.db = db
        self.loop = asyncio.get_event_loop()

        super().__init__(logging.ERROR)

    def emit(self, record):
        self.loop.create_task(self.db.create_error_report(record))

# Handlers
DATABASE_HANDLER = None # must be setup on init
FILE_HANDLER = handlers.RotatingFileHandler(filename="logs/medb.log", maxBytes=5 * 1024 * 1024, backupCount=3) # Max size of 5Mb per-file, with 3 past files
LOG_FORMATTER = logging.Formatter("%(asctime)s %(levelname)s | [module %(module)s -> function %(funcName)s] (%(filename)s:%(lineno)s) | %(message)s")

FILE_HANDLER.setLevel(logging.NOTSET)
FILE_HANDLER.setFormatter(LOG_FORMATTER)

# Set log level according to debug status (call once at init)
def set_level(debug=False):
    global LOG_LEVEL

    LOG_LEVEL = logging.DEBUG if debug == True else logging.INFO

# Setup database handler
def set_database(db):
    global DATABASE_HANDLER

    DATABASE_HANDLER = DatabaseErrorHandler(db)

# Special logger that runs for each module it's called in
def get_logger():
    # Get name of calling module
    call_frame = inspect.stack()[1]
    call_module = inspect.getmodule(call_frame[0])
    module_name = call_module.__name__

    # Setup custom FileHandler logger
    module_logger = logging.getLogger(module_name)
    module_logger.setLevel(LOG_LEVEL)
    module_logger.addHandler(FILE_HANDLER)

    if DATABASE_HANDLER is not None:
        module_logger.addHandler(DATABASE_HANDLER)

    # don't leak stack frames, kthx
    del call_frame
    del call_module

    return module_logger
