#!/usr/bin/env python3
"""Automated end-to-end browser GUI test suite for Script Logs error acknowledgment.

Validates Script Logs tab badges, status banner, click event handling for 'Acknowledge Errors',
and live server-authoritative status updates in a headless Chromium environment per Rule 7.
"""

from __future__ import annotations

import os
import unittest

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class TestScriptLogsGUI(unittest.TestCase):
    """End-to-end browser GUI test suite for script log acknowledgment."""

    driver: webdriver.Chrome
    harness_url: str

    @classmethod
    def setUpClass(cls) -> None:
        """Initializes headless Chrome webdriver for automated GUI testing."""
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        harness_path = os.path.join(repo_root, "tests", "gui", "script_logs_test_harness.html")
        cls.harness_url = f"file://{harness_path}#scriptlogs"

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--allow-file-access-from-files")
        chrome_options.add_argument("--window-size=1280,900")
        cls.driver = webdriver.Chrome(options=chrome_options)

    @classmethod
    def tearDownClass(cls) -> None:
        """Tears down the headless Chrome webdriver instance."""
        if hasattr(cls, "driver") and cls.driver:
            cls.driver.quit()

    def setUp(self) -> None:
        """Navigates to the test harness HTML before each test."""
        self.driver.get(self.harness_url)
        self.driver.refresh()
        WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located((By.ID, "sl-ack"))
        )

    def test_no_javascript_runtime_errors(self) -> None:
        """Verifies zero JavaScript console or runtime errors during initialization."""
        errors = self.driver.execute_script("return window.errors || [];")
        self.assertEqual(len(errors), 0, f"Unexpected JS errors: {errors}")

    def test_initial_unacknowledged_error_state(self) -> None:
        """Verifies that unacknowledged errors display NEW ERROR badge and warning banner."""
        # Wait for log lines to load
        WebDriverWait(self.driver, 5).until(
            lambda d: "Sync connection timeout" in d.find_element(By.ID, "sl-content").text
        )

        badge = self.driver.find_element(By.ID, "sl-badge-sync")
        self.assertIn("NEW ERROR", badge.text)

        banner = self.driver.find_element(By.ID, "sl-status-banner")
        self.assertIn("New errors detected since last acknowledgment", banner.text)

    def test_click_acknowledge_errors_syncs_with_server(self) -> None:
        """Verifies that clicking 'Acknowledge Errors' calls the server API and updates UI."""
        # Wait for log lines to be visible
        WebDriverWait(self.driver, 5).until(
            lambda d: "Sync connection timeout" in d.find_element(By.ID, "sl-content").text
        )

        ack_btn = self.driver.find_element(By.ID, "sl-ack")
        ack_btn.click()

        # Wait for acknowledgment API call to complete and UI to update
        WebDriverWait(self.driver, 5).until(
            lambda d: "All script log entries acknowledged" in d.find_element(By.ID, "sl-status-banner").text
        )

        # Assert server API was called with log=sync
        calls = self.driver.execute_script("return window._ack_calls || [];")
        self.assertTrue(any("ack_script_log?log=sync" in call for call in calls))

        # Assert badge changed to OK
        badge = self.driver.find_element(By.ID, "sl-badge-sync")
        self.assertIn("OK", badge.text)

        # Assert banner changed to OK
        banner = self.driver.find_element(By.ID, "sl-status-banner")
        self.assertIn("All script log entries acknowledged. No new alerts.", banner.text)


if __name__ == "__main__":
    unittest.main()
