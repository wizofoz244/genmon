"""Common test setup and mocking helper for Genmon test suite."""

import logging
import sys
from unittest.mock import MagicMock

class MockModule(MagicMock):
    """MagicMock subclass that simulates a module with nested attributes."""
    pass

MOCK_MODULE_NAMES = [
    "flask",
    "flask.views",
    "flask_login",
    "pyotp",
    "requests",
    "croniter",
    "serial",
    "idna",
    "cryptography",
    "cryptography.hazmat",
    "cryptography.hazmat.backends",
    "cryptography.hazmat.primitives",
    "cryptography.hazmat.primitives.ciphers",
    "netifaces",
    "urllib3",
    "certifi",
    "bs4",
    "twopy",
    "RPi",
    "RPi.GPIO",
    "smbus",
    "paho",
    "paho.mqtt",
    "paho.mqtt.client",
    "crcmod",
]

for mod_name in MOCK_MODULE_NAMES:
    if mod_name not in sys.modules:
        try:
            __import__(mod_name)
        except ImportError:
            sys.modules[mod_name] = MockModule()

if "flask" in sys.modules and isinstance(sys.modules["flask"], MockModule):
    mock_app = MagicMock()
    mock_app.route = lambda *args, **kwargs: (lambda f: f)
    mock_app.before_request = lambda f: f
    mock_app.after_request = lambda f: f
    sys.modules["flask"].Flask.return_value = mock_app

# Safe logger setup for unprivileged test execution (avoids /var/log permission errors)
try:
    import genmonlib.mylog
    def safe_setup_logger(logger_name, log_file, level=logging.INFO, stream=False):
        return logging.getLogger(logger_name)
    genmonlib.mylog.SetupLogger = safe_setup_logger
except Exception:
    pass
