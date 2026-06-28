import logging
import sys
import os

FORMATTER = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(message)s "
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")


def get_console_handler():
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(FORMATTER)
    return console_handler


def get_logger(logger_name):
    logger = logging.getLogger(logger_name)
    if LOG_LEVEL == "DEBUG":
        set_level = logging.DEBUG
    elif LOG_LEVEL == "INFO":
        set_level = logging.INFO
    else:
        set_level = logging.WARN

    logger.setLevel(set_level)
    logger.addHandler(get_console_handler())
    logger.propagate = False
    return logger
