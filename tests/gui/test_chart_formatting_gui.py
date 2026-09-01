#!/usr/bin/env python3
"""Automated end-to-end browser GUI test suite for telemetry chart formatting.

Validates chart controls, mode toggling (Trend/Dual/Raw), live summary statistics,
and intelligent axis scaling in a headless Chromium environment per Rule 7.
"""

from __future__ import annotations

import os
import unittest
from typing import Any, Dict, List

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class TestChartFormattingGUI(unittest.TestCase):
    """End-to-end browser GUI test suite for telemetry chart formatting."""

    driver: webdriver.Chrome
    harness_url: str

    @classmethod
    def setUpClass(cls) -> None:
        """Initializes headless Chrome webdriver for automated GUI testing."""
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        harness_path = os.path.join(repo_root, "tests", "gui", "chart_test_harness.html")
        cls.harness_url = f"file://{harness_path}"

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
        WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located((By.ID, "temp-chart-pi-voltage"))
        )

    def test_no_javascript_runtime_errors(self) -> None:
        """Verifies zero JavaScript console or runtime errors during initialization."""
        errors = self.driver.execute_script("return window.errors || [];")
        self.assertEqual(len(errors), 0, f"Unexpected JS errors: {errors}")

    def test_summary_statistics_displayed_and_calculated(self) -> None:
        """Verifies that live summary statistics (Cur, Min, Max, Avg) render correctly."""
        stats_container = self.driver.find_element(By.ID, "chart-stats-pi-voltage")
        self.assertTrue(stats_container.is_displayed())

        cur_text = stats_container.find_element(By.CSS_SELECTOR, ".val-cur").text
        min_text = stats_container.find_element(By.CSS_SELECTOR, ".val-min").text
        max_text = stats_container.find_element(By.CSS_SELECTOR, ".val-max").text
        avg_text = stats_container.find_element(By.CSS_SELECTOR, ".val-avg").text

        self.assertIn("V", cur_text)
        self.assertIn(min_text, ["1.23 V", "1.24 V"])
        self.assertIn(max_text, ["1.34 V", "1.35 V"])
        self.assertIn("V", avg_text)

    def test_mode_toggling_trend_dual_raw(self) -> None:
        """Verifies interactive mode switching between Trend, Dual, and Raw views."""
        tile = self.driver.find_element(By.CSS_SELECTOR, '[data-tile="tempchart-pi-voltage"]')

        trend_btn = tile.find_element(By.CSS_SELECTOR, '.chart-mode-btn[data-mode="trend"]')
        dual_btn = tile.find_element(By.CSS_SELECTOR, '.chart-mode-btn[data-mode="dual"]')
        raw_btn = tile.find_element(By.CSS_SELECTOR, '.chart-mode-btn[data-mode="raw"]')

        # Default mode for voltage is trend
        self.assertIn("active", trend_btn.get_attribute("class"))
        datasets_count = self.driver.execute_script(
            "return Genmon.pages.status._tempCharts['Pi Voltage'].chart.data.datasets.length;"
        )
        self.assertEqual(datasets_count, 1)

        # Click Dual mode
        dual_btn.click()
        self.assertIn("active", dual_btn.get_attribute("class"))
        self.assertNotIn("active", trend_btn.get_attribute("class"))
        datasets_count = self.driver.execute_script(
            "return Genmon.pages.status._tempCharts['Pi Voltage'].chart.data.datasets.length;"
        )
        self.assertEqual(datasets_count, 2)

        # Click Raw mode
        raw_btn.click()
        self.assertIn("active", raw_btn.get_attribute("class"))
        self.assertNotIn("active", dual_btn.get_attribute("class"))
        datasets_count = self.driver.execute_script(
            "return Genmon.pages.status._tempCharts['Pi Voltage'].chart.data.datasets.length;"
        )
        self.assertEqual(datasets_count, 1)
        dataset_fill = self.driver.execute_script(
            "return Genmon.pages.status._tempCharts['Pi Voltage'].chart.data.datasets[0].fill;"
        )
        self.assertFalse(dataset_fill, "Raw mode for voltage must not fill area")

    def test_intelligent_voltage_y_axis_padding(self) -> None:
        """Verifies that the Y-axis enforces a minimum span so micro-stepping does not fill 100% height."""
        y_min = self.driver.execute_script(
            "return Genmon.pages.status._tempCharts['Pi Voltage'].chart.options.scales.y.min;"
        )
        y_max = self.driver.execute_script(
            "return Genmon.pages.status._tempCharts['Pi Voltage'].chart.options.scales.y.max;"
        )
        span = y_max - y_min
        self.assertGreaterEqual(span, 0.35, f"Expected minimum 0.35V visible height, got {span:.2f}V")


if __name__ == "__main__":
    unittest.main()
