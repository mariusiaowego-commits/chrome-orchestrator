from __future__ import annotations

from pathlib import Path

from chrome_orchestrator.classify import (
    classify_binary,
    extract_port,
    extract_udd,
    is_helper,
    read_devtools_port,
)

SYSTEM_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SYSTEM_CHROME_HELPER = (
    "/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework.framework"
    "/Versions/1.0/Helpers/Google Chrome Helper.app/Contents/MacOS/Google Chrome Helper"
)
PLAYWRIGHT_CHROMIUM = (
    "/opt/ms-playwright/chromium-1223/chrome-mac/Chromium.app/Contents/MacOS/Chromium"
)
HEADLESS_SHELL = (
    "/opt/ms-playwright/chromium_headless_shell-1223"
    "/chrome-headless-shell-mac-arm64/chrome-headless-shell"
)


def test_classifies_chrome_family() -> None:
    assert classify_binary(SYSTEM_CHROME) == "system-chrome"
    assert classify_binary(SYSTEM_CHROME_HELPER) == "system-chrome"
    assert classify_binary(PLAYWRIGHT_CHROMIUM) == "playwright-chromium"
    assert classify_binary(HEADLESS_SHELL) == "headless-shell"


def test_excludes_electron_and_cef_apps() -> None:
    excluded = [
        "/Applications/Obsidian.app/Contents/Frameworks/Obsidian Helper.app"
        "/Contents/MacOS/Obsidian Helper",
        "/Applications/Grok Bot.app/Contents/Frameworks/Grok Bot Helper.app"
        "/Contents/MacOS/Grok Bot Helper",
        "/Applications/ChatGPT.app/Contents/Frameworks/Codex Framework.framework"
        "/Versions/1/Helpers/browser",
        "/Applications/Battle.net.app/Contents/Frameworks/Battle.net Helper.app"
        "/Contents/MacOS/Battle.net Helper",
    ]
    for exe in excluded:
        assert classify_binary(exe) is None, exe


def test_helper_detection() -> None:
    assert is_helper((SYSTEM_CHROME, "--type=renderer"))
    crashpad = "/Applications/Google Chrome.app/Contents/Frameworks/x/chrome_crashpad_handler"
    assert is_helper((crashpad,))
    assert not is_helper((SYSTEM_CHROME,))


def test_extracts_launch_flags() -> None:
    cmdline = (
        HEADLESS_SHELL,
        "--remote-debugging-port=9223",
        "--user-data-dir=/tmp/profiles/example",
        "--headless",
    )
    assert extract_port(cmdline) == 9223
    assert extract_udd(cmdline) == "/tmp/profiles/example"
    assert extract_port((SYSTEM_CHROME,)) is None


def test_devtools_active_port_file(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "DevToolsActivePort").write_text("9223\n/devtools/browser/abc\n")
    assert read_devtools_port(str(profile)) == 9223
    assert read_devtools_port(str(tmp_path / "missing")) is None
