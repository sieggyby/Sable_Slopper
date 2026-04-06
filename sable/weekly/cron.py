"""Launchd plist generator for sable weekly."""
from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent

from sable.shared.paths import sable_home

PLIST_LABEL = "com.sable.weekly"
PLIST_FILENAME = f"{PLIST_LABEL}.plist"


def _venv_sable_path() -> str:
    """Return the path to the sable executable in the current venv."""
    venv = Path(sys.executable).parent
    sable_bin = venv / "sable"
    if sable_bin.exists():
        return str(sable_bin)
    return f"{sys.executable} -m sable"


def generate_plist() -> str:
    """Generate a launchd plist for weekly --all --json-log on Monday 06:00."""
    sable_bin = _venv_sable_path()
    working_dir = Path(__file__).resolve().parents[2]  # Sable_Slopper root
    logs_dir = sable_home() / "logs"

    return dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
          <key>Label</key>
          <string>{PLIST_LABEL}</string>

          <key>ProgramArguments</key>
          <array>
            <string>{sable_bin}</string>
            <string>--json-log</string>
            <string>weekly</string>
            <string>run</string>
            <string>--all</string>
          </array>

          <key>WorkingDirectory</key>
          <string>{working_dir}</string>

          <key>StartCalendarInterval</key>
          <dict>
            <key>Weekday</key>
            <integer>1</integer>
            <key>Hour</key>
            <integer>6</integer>
            <key>Minute</key>
            <integer>0</integer>
          </dict>

          <key>RunAtLoad</key>
          <false/>

          <key>StandardOutPath</key>
          <string>{logs_dir}/weekly-stdout.log</string>

          <key>StandardErrorPath</key>
          <string>{logs_dir}/weekly-stderr.log</string>
        </dict>
        </plist>
    """)


def install_plist() -> Path:
    """Write the plist to ~/Library/LaunchAgents/ and return the path."""
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)

    # Ensure logs dir exists
    logs_dir = sable_home() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    plist_path = plist_dir / PLIST_FILENAME
    plist_path.write_text(generate_plist(), encoding="utf-8")
    return plist_path
