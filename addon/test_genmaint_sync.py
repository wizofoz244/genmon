#!/usr/bin/env python3
"""Backward-compatible runner for GenMaintSync unit tests."""

import os
import sys
import unittest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
)

from tests.unit.test_genmaint_sync import TestGenMaintSync

if __name__ == "__main__":
    unittest.main()
