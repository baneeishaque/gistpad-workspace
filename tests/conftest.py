"""Pytest configuration: opt-in live tests via ``--run-live``."""

from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run live integration tests against the real GitHub API",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "live: integration tests against the real GitHub API")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skip = pytest.mark.skip(reason="need --run-live to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
