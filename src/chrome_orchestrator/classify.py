from __future__ import annotations

import os
from pathlib import Path

SYSTEM_CHROME_BUNDLE = "/Applications/Google Chrome.app/"
GOOGLE_CHROME_FRAMEWORK = "/Contents/Frameworks/Google Chrome Framework.framework/"
PLAYWRIGHT_MARK = "/ms-playwright/"
HEADLESS_SHELL_NAME = "chrome-headless-shell"
ELECTRON_MARK = "/Contents/Frameworks/Electron Framework.framework/"
CEF_MARK = "/Chromium Embedded Framework.framework/"

CHROME_KINDS = ("system-chrome", "playwright-chromium", "headless-shell", "unknown-chromium")


def classify_binary(exe: str) -> str | None:
    """Map an executable path to a Chrome kind, or None for everything else.

    Classification is path-based on purpose: process names collide with
    Electron and CEF apps that reuse the Chromium framework.
    """
    if not exe:
        return None
    if HEADLESS_SHELL_NAME in exe and PLAYWRIGHT_MARK in exe:
        return "headless-shell"
    if PLAYWRIGHT_MARK in exe and "/Chromium.app/" in exe:
        return "playwright-chromium"
    if exe.startswith(SYSTEM_CHROME_BUNDLE) and (
        GOOGLE_CHROME_FRAMEWORK in exe or exe.endswith("/Contents/MacOS/Google Chrome")
    ):
        return "system-chrome"
    if ELECTRON_MARK in exe or CEF_MARK in exe:
        return None
    name = os.path.basename(exe).lower()
    if name.startswith(("chrome", "chromium")):
        return "unknown-chromium"
    return None


def is_helper(cmdline: tuple[str, ...]) -> bool:
    if any(arg.startswith("--type=") for arg in cmdline):
        return True
    return "crashpad" in os.path.basename(cmdline[0]).lower() if cmdline else False


def extract_udd(cmdline: tuple[str, ...]) -> str | None:
    for arg in cmdline:
        if arg.startswith("--user-data-dir="):
            return arg.split("=", 1)[1].strip('"')
    return None


def extract_port(cmdline: tuple[str, ...]) -> int | None:
    for arg in cmdline:
        if arg.startswith("--remote-debugging-port="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                return None
    return None


def read_devtools_port(user_data_dir: str | None) -> int | None:
    if not user_data_dir:
        return None
    try:
        first = (Path(user_data_dir) / "DevToolsActivePort").read_text().splitlines()[0]
        return int(first)
    except (OSError, ValueError, IndexError):
        return None
