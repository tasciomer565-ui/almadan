"""Playwright E2E test konfigürasyonu."""
import pytest
from playwright.sync_api import Playwright, sync_playwright


@pytest.fixture(scope="session")
def browser_type_launch_args():
    return {"headless": True, "args": ["--disable-web-security"]}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "ignore_https_errors": True,
        "viewport": {"width": 1280, "height": 800},
        "locale": "tr-TR",
        "timezone_id": "Europe/Istanbul",
    }
