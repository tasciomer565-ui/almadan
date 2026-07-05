"""Playwright E2E test konfigürasyonu."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Playwright E2E testlerini calistir.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: Playwright tabanli uc uca testler")


def pytest_collection_modifyitems(config, items):
    e2e_items = [
        item
        for item in items
        if "tests/e2e" in Path(str(item.fspath)).as_posix()
    ]
    if not e2e_items:
        return

    if not config.getoption("--run-e2e"):
        skip_e2e = pytest.mark.skip(reason="E2E testleri icin --run-e2e kullanin.")
    elif importlib.util.find_spec("pytest_playwright") is None:
        skip_e2e = pytest.mark.skip(reason="pytest-playwright kurulu degil.")
    else:
        return

    for item in e2e_items:
        item.add_marker(skip_e2e)


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
