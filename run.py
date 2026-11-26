#!/usr/bin/env python3
"""AWAGO launcher — one command to run everything (Windows / macOS / Linux).

Usage
-----
    python run.py                 # bootstrap, seed, start server, open browser
    python run.py --no-browser    # start without opening a browser
    python run.py --host 0.0.0.0  # expose to the local network (see warning in README)
    python run.py --skip-seed     # do not seed even if the database is empty
    python run.py --skip-train    # do not auto-train even if no models exist

The launcher:
  1. verifies Python >= 3.10,
  2. creates .venv and installs requirements (only when needed),
  3. copies .env.example -> .env if missing,
  4. initializes the database,
  5. seeds initial data when the database is empty (Demo or real per DATA_MODE),
  6. optionally trains lightweight models on first run (AUTO_TRAIN_ON_SEED),
  7. starts the server at http://HOST:PORT and opens the default browser.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
VENV_DIR = REPO_ROOT / ".venv"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
DEPS_HASH_FILE = VENV_DIR / ".awago_deps_hash"
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

MIN_PYTHON = (3, 10)


# ----------------------------------------------------------------------
# Bootstrap steps (kept importable for tests)
# ----------------------------------------------------------------------

def check_python() -> None:
    if sys.version_info < MIN_PYTHON:
        major, minor = MIN_PYTHON
        sys.exit(
            f"ERROR: Python {major}.{minor}+ is required, but this is Python "
            f"{sys.version.split()[0]}.\nPlease install a newer Python from https://python.org "
            "and re-run this launcher."
        )


def in_project_venv() -> bool:
    return Path(sys.prefix).resolve() == VENV_DIR.resolve()


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def deps_hash() -> str:
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def deps_installed() -> bool:
    return DEPS_HASH_FILE.exists() and DEPS_HASH_FILE.read_text().strip() == deps_hash()


def ensure_venv() -> Path:
    """Create .venv if needed and install requirements when the hash changed."""
    if not VENV_DIR.exists():
        print("* Creating virtual environment in .venv ...")
        try:
            subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        except subprocess.CalledProcessError:
            sys.exit(
                "ERROR: could not create the .venv virtual environment.\n"
                "Make sure the 'venv' module is available (on Debian/Ubuntu: "
                "sudo apt install python3-venv)."
            )
    python = venv_python()
    if not python.exists():
        sys.exit(f"ERROR: venv python not found at {python}. Delete .venv and re-run.")
    if not deps_installed():
        print("* Installing dependencies (requirements.txt changed or first run) ...")
        cmd = [str(python), "-m", "pip", "install", "--upgrade", "pip"]
        subprocess.run(cmd, check=False)
        cmd = [str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            sys.exit(
                "ERROR: dependency installation failed. Check your internet connection\n"
                "or install manually: .venv/bin/pip install -r requirements.txt"
            )
        DEPS_HASH_FILE.write_text(deps_hash())
    return python


def ensure_env_file() -> None:
    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        print("* Created .env from .env.example (edit it to change defaults).")


def port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


# ----------------------------------------------------------------------
# First-run data / model bootstrap (runs inside the venv)
# ----------------------------------------------------------------------

def bootstrap_data(skip_seed: bool, skip_train: bool) -> None:
    from app.config import get_settings
    from app.db.engine import init_db, session_scope
    from app.db.models import ModelArtifact
    from app.logging_config import setup_logging
    from app.services.market import collect_data, count_bars, ensure_pairs

    settings = get_settings()
    setup_logging(settings.logs_dir, settings.log_level)
    init_db()

    with session_scope() as session:
        ensure_pairs(session, settings)
        bar_count = count_bars(session)

    if bar_count == 0 and not skip_seed:
        print("* Database is empty — seeding initial data "
              f"(DATA_MODE={settings.data_mode}) ...")
        if settings.data_mode == "demo":
            # Explicit demo seeding (works fully offline).
            from datetime import date, timedelta

            from app.services.data_providers.demo import DemoProvider

            from app.services.market import upsert_bars

            provider = DemoProvider(seed=settings.demo_seed)
            end = date.today()
            start = end - timedelta(days=settings.history_days)
            with session_scope() as session:
                for symbol in settings.pairs_list:
                    bars = provider.fetch_history(symbol, start, end)
                    inserted = upsert_bars(session, symbol, bars, data_source="demo")
                    print(f"    {symbol}: {inserted} demo bars")
            print("    NOTE: seeded data is synthetic DEMO data (clearly flagged in the UI).")
        else:
            from app.api.errors import AppError

            try:
                with session_scope() as session:
                    summary = collect_data(session, settings)
                src = summary.get("data_source")
                print(f"    Seeded from source: {src}")
                if summary.get("fallback_used"):
                    print("    WARNING: real source unreachable — DEMO fallback data was used "
                          "and is clearly flagged in the UI.")
            except AppError as exc:
                print(f"    ERROR: {exc.message}")
            except Exception as exc:  # noqa: BLE001
                print(f"    ERROR: seeding failed: {exc}")
                if not settings.fallback_to_demo:
                    print("    (FALLBACK_TO_DEMO=false in .env — starting without data.)")

    if not skip_train and settings.auto_train_on_seed:
        from sqlalchemy import select

        with session_scope() as session:
            n_models = len(list(session.scalars(select(ModelArtifact)).all()))
        if n_models == 0:
            print("* No trained models found — running first-run training "
                  "(AUTO_TRAIN_ON_SEED=true; later trainings can be run from the dashboard).")
            from app.services.forecasting.training import train_pair

            for symbol in settings.pairs_list:
                try:
                    with session_scope() as session:
                        train_pair(session, symbol, settings=settings, quick=True,
                                   progress=lambda f, m: None)
                    print(f"    {symbol}: trained")
                except Exception as exc:  # noqa: BLE001
                    print(f"    {symbol}: skipped ({exc})")


# ----------------------------------------------------------------------
# Server
# ----------------------------------------------------------------------

def open_browser_later(url: str, delay: float = 1.8) -> None:
    def _open() -> None:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    threading.Timer(delay, _open).start()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AWAGO launcher")
    parser.add_argument("--host", default=None, help="Bind host (default: HOST from .env or 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (default: PORT from .env or 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the default browser.")
    parser.add_argument("--skip-seed", action="store_true", help="Never seed data automatically.")
    parser.add_argument("--skip-train", action="store_true", help="Never auto-train models.")
    return parser.parse_args()


def main() -> int:
    check_python()

    if not in_project_venv():
        python = ensure_venv()
        print(f"* Launching inside the project virtual environment ({python})")
        env = os.environ.copy()
        env["AWAGO_LAUNCHED"] = "1"
        os.execve(str(python), [str(python), str(REPO_ROOT / "run.py"), *sys.argv[1:]], env)

    ensure_env_file()

    args = parse_args()
    from app.config import get_settings

    settings = get_settings()
    host = args.host or settings.host
    port = args.port or settings.port

    bootstrap_data(skip_seed=args.skip_seed, skip_train=args.skip_train)

    if not port_available(host, port):
        print(
            f"\nERROR: port {port} on {host} is already in use.\n"
            f"  - Stop the other program, or\n"
            f"  - Choose another port: edit PORT in .env or run: python run.py --port 8001"
        )
        return 1

    url = f"http://{host}:{port}"
    if host == "0.0.0.0":
        url_shown = "http://127.0.0.1:" + str(port)
    else:
        url_shown = url
    print(f"\n  AWAGO is running at {url_shown}")
    print("  API docs:  " + url_shown + "/docs")
    print("  Press Ctrl+C to stop.\n")

    open_browser_flag = settings.open_browser and not args.no_browser
    if open_browser_flag:
        open_browser_later(url_shown)

    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, log_level=settings.log_level.lower())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nAWAGO stopped.")
        raise SystemExit(0)
