# -------------------------------------------------------------------------------
# PURPOSE: setup logging
#
#  AUTHOR: Jason G Yates
#    DATE: 03-Dec-2016
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------
import logging
import logging.handlers


# ---------- SetupLogger --------------------------------------------------------
def SetupLogger(logger_name, log_file, level=logging.INFO, stream=False):

    logger = logging.getLogger(logger_name)

    # remove existing logg handlers
    for handler in logger.handlers[:]:  # make a copy of the list
        logger.removeHandler(handler)

    logger.setLevel(level)

    if log_file != "":
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        rotate = logging.handlers.RotatingFileHandler(
            log_file, mode="a", maxBytes=50000, backupCount=5
        )
        rotate.setFormatter(formatter)
        logger.addHandler(rotate)

    if stream:  # print to screen also?
        streamHandler = logging.StreamHandler()
        formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        streamHandler.setFormatter(formatter)
        logger.addHandler(streamHandler)

    return logging.getLogger(logger_name)
