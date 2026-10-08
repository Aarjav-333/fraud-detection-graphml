"""Plant a scripted fraud operation and run the full detection pipeline on it.

Made for live demos and the project report: every run plants the same accounts
and transactions, so the story is repeatable and easy to find in the UI
(search for "DEMO-").

The scenario - a mule network laundering money (all ids start with DEMO-):
  1. Collection    9 feeder accounts pay a mule account opened 6 days earlier,
                   all within 25 minutes                  -> R4 fan-in, R3 new account
  2. Consolidation the mule forwards everything to a collector -> R1 large amount
  3. Layering      collector -> shell 1 -> shell 2 -> collector, each hop kept
                   under Rs 1,00,000 so R1 misses it           -> R6 circular
  4. Cash-out      the collector splits money into 9 transfers just under
                   Rs 1,00,000 to 9 cash-out accounts in 8 minutes -> R2 rapid, R5 fan-out

Like every account in the synthetic dataset, each demo account also gets ~30
ordinary transactions with real customers over 2024, so it looks like a normal
customer to the graph and ML steps instead of an isolated island.

Demo accounts are inserted with is_fraud=0 (an operation nobody has confirmed
yet), so the supervised model is never told they are fraud: a high ML score is
the model generalizing, not memorizing. Side effect: the rule engine's precision
figure counts the demo transactions as false positives.

Your own data is never changed. The demo works on a copy in data/demo/: your
database, saved_models/ and features.csv are copied there, the scenario is
planted into the copy, and the pipeline writes its outputs there too.

Run from the backend/ folder, after init_db + seed_data:
    python -m scripts.demo_scenario               # copy, plant, run the pipeline, report
    python -m scripts.demo_scenario --plant-only  # copy and plant; run the pipeline from the UI
    python -m scripts.demo_scenario --serve       # run the backend on the copy, for the UI
    python -m scripts.demo_scenario --cleanup     # delete the copy

--serve uses port 8000 like the normal backend (so the frontend needs no
changes): stop the normal backend first. While it runs, planting again and
--cleanup refuse to start. Planting again builds a fresh copy of your current
data next to the old one and only replaces it once planting has worked.

The planting itself lives in scripts/demo_plant.py.
"""
import argparse
import errno
import os
import shutil
import socket
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import uvicorn
from sqlalchemy.engine import make_url

from app.config import BACKEND_DIR, settings
from scripts.demo_common import (BUILD_DIR, DATABASE_NAME, DEMO_DIR, OLD_DIR, PREFIX, PREFIX_END,
                                 demo_settings, point_app_at)

DEMO_PORT = 8000                                            # where the frontend's VITE_API_URL points
COPY_TIMEOUT = 60                                           # seconds to wait for a locked database
LOCK_FILE = os.path.join(BACKEND_DIR, "data", "demo.lock")  # held while a demo command runs (gitignored)
DEMO_BUSY = ("The demo copy is in use: stop the demo backend (--serve), or wait for the other "
             "demo command to finish.")

if os.name == "nt":
    import msvcrt

    def _lock(fh) -> bool:
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno == errno.EACCES:   # another process holds it
                return False
            raise
        return True

    def _unlock(fh):
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(fh) -> bool:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:   # another process holds it
            return False
        return True

    def _unlock(fh):
        fcntl.flock(fh, fcntl.LOCK_UN)

# Older versions of this script planted into the real data
LEGACY_SNAPSHOT_DIR = os.path.join(BACKEND_DIR, "data", "demo_snapshot")
LEGACY_STATE = os.path.join(settings.saved_models_dir, "demo_state.json")
LEGACY_HELP = """\
An older version of this script planted the demo into your real data (DEMO- rows
in the database, or a data/demo_snapshot/ folder). Undo it with that version's
own cleanup, from the backend/ folder:
  git restore --source d3dbd1b scripts/demo_scenario.py
  python -m scripts.demo_scenario --cleanup
  git restore scripts/demo_scenario.py"""


# ------------------------------------------------------------- the real data

def _database_file() -> str | None:
    """The app's SQLite database file, or None if it doesn't use one."""
    url = make_url(settings.DATABASE_URL)
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        return None
    return os.path.abspath(url.database)


def _source_database() -> str:
    path = _database_file()
    if path is None:
        raise SystemExit("The demo copies the database file, so it needs a SQLite DATABASE_URL.")
    if not os.path.isfile(path):
        raise SystemExit(f"No database at {path}. Set it up first:\n  python -m scripts.init_db\n"
                         "  python -m data.generate_synthetic\n  python -m scripts.seed_data")
    for folder in (DEMO_DIR, BUILD_DIR, OLD_DIR):
        if os.path.normcase(path).startswith(os.path.normcase(folder + os.sep)):
            raise SystemExit(f"DATABASE_URL points into {folder}, a demo copy. Unset it first.")
    return path


def _open_read_only(path: str) -> sqlite3.Connection:
    # Read-only: the real database is never changed, and a missing file is an
    # error rather than a new empty database
    return sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)


def _has_legacy_demo(database: str | None) -> bool:
    if os.path.isdir(LEGACY_SNAPSHOT_DIR):
        return True
    if database is None or not os.path.isfile(database):
        return False
    con = _open_read_only(database)
    try:
        return con.execute("SELECT 1 FROM accounts WHERE account_uid >= ? AND account_uid < ? LIMIT 1",
                           (PREFIX, PREFIX_END)).fetchone() is not None
    except sqlite3.Error:   # no accounts table yet, or locked (the copy reports that properly)
        return False
    finally:
        con.close()


# ------------------------------------------------------------------- the copy

def _sqlite_copy(source: str, target: str) -> None:
    """Copy a SQLite database with its backup API, which is consistent even
    while the dev server is using it."""
    deadline = time.monotonic() + COPY_TIMEOUT

    def give_up_when_stuck(status, remaining, total):
        if time.monotonic() > deadline:   # backup() itself retries a locked database forever
            raise TimeoutError

    src = _open_read_only(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst, progress=give_up_when_stuck)
    except TimeoutError:
        raise SystemExit(f"{source} stayed locked for over {COPY_TIMEOUT}s. Is a pipeline step "
                         "running in the app? Try again when it finishes.") from None
    except sqlite3.Error as exc:
        raise SystemExit(f"Couldn't copy {source}: {exc}") from None
    finally:
        src.close()
        dst.close()


def _delete_folder(folder: str) -> bool:
    if not os.path.exists(folder):
        return False
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        raise SystemExit(f"Couldn't delete {folder}: {exc.strerror}. "
                         "Close any program using its files and try again.") from None
    return True


def _copy_real_data(source: str, folder: str) -> None:
    """Copy the database and pipeline outputs into folder. Only reads the originals."""
    target = demo_settings(folder)
    os.makedirs(target.saved_models_dir)
    os.makedirs(target.processed_dir)
    _sqlite_copy(source, os.path.join(folder, DATABASE_NAME))
    if os.path.isdir(settings.saved_models_dir):
        for name in os.listdir(settings.saved_models_dir):
            path = os.path.join(settings.saved_models_dir, name)
            if os.path.isfile(path):
                shutil.copy2(path, target.saved_models_dir)
    if os.path.isfile(settings.features_csv):
        shutil.copy2(settings.features_csv, target.processed_dir)
    print("Copied your database and pipeline outputs.")


def _tidy_leftovers() -> None:
    """Clear what an interrupted run left behind: a half-built copy, or the
    previous demo moved aside mid-swap (put back if nothing replaced it)."""
    _delete_folder(BUILD_DIR)
    if os.path.exists(OLD_DIR):
        if os.path.exists(DEMO_DIR):
            _delete_folder(OLD_DIR)
        else:
            os.rename(OLD_DIR, DEMO_DIR)


def _swap_in_build() -> None:
    """Replace the previous demo with the new build: move the old one aside,
    move the new one in, then delete the old one. Each move is a rename, so
    there is always one complete demo (see _tidy_leftovers)."""
    moved_aside = False
    try:
        if os.path.exists(DEMO_DIR):
            os.rename(DEMO_DIR, OLD_DIR)
            moved_aside = True
        os.rename(BUILD_DIR, DEMO_DIR)
    except OSError as exc:
        if moved_aside:
            os.rename(OLD_DIR, DEMO_DIR)   # put the previous demo back
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        raise SystemExit(f"Couldn't replace the previous demo in {DEMO_DIR}: {exc.strerror}. "
                         "Close any program using its files and try again.") from None
    shutil.rmtree(OLD_DIR, ignore_errors=True)   # if a file is still open, the next run removes it


# ---------------------------------------------------------------- the commands

@contextmanager
def _demo_lock():
    """One demo command at a time: --serve holds this for as long as the demo
    backend runs, so planting or cleaning up can't swap the copy out from under
    it. The OS releases the lock when the process ends, however it ends."""
    with open(LOCK_FILE, "a") as fh:
        if not _lock(fh):
            raise SystemExit(DEMO_BUSY)
        try:
            yield
        finally:
            _unlock(fh)


def build(plant_only: bool) -> None:
    """Copy the real data into BUILD_DIR, plant and run there, then swap it in
    for the previous demo. A failure leaves the previous demo as it was."""
    source = _source_database()
    if _has_legacy_demo(source):
        raise SystemExit(LEGACY_HELP)
    with _demo_lock():
        _tidy_leftovers()
        try:
            _copy_real_data(source, BUILD_DIR)
            engine = point_app_at(BUILD_DIR)   # from here on, this process only sees the copy
            try:
                from scripts import demo_plant   # the ML stack: imported only now that it's needed

                if hasattr(sys.stdout, "reconfigure"):   # rule labels use symbols cp1252 lacks
                    sys.stdout.reconfigure(encoding="utf-8")
                demo_plant.run(plant_only)
            finally:
                engine.dispose()   # close the copy's connections so its folder can be moved
        except BaseException:
            shutil.rmtree(BUILD_DIR, ignore_errors=True)
            raise
        _swap_in_build()


def _port_in_use(port: int) -> bool:
    # Connect rather than bind: this also sees a server listening on 0.0.0.0,
    # and isn't fooled by closed connections still in TIME_WAIT
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def serve() -> None:
    """Run the backend on the demo copy in this process, so the lock lasts
    exactly as long as the server does."""
    with _demo_lock():
        _tidy_leftovers()
        if not os.path.isfile(os.path.join(DEMO_DIR, DATABASE_NAME)):
            raise SystemExit("There's no demo copy yet. Make one first: python -m scripts.demo_scenario")
        if _port_in_use(DEMO_PORT):
            raise SystemExit(f"Port {DEMO_PORT} is in use. Stop your normal backend "
                             "(Ctrl+C in its terminal) and try again.")
        point_app_at(DEMO_DIR)
        print(f"Serving the demo copy on http://127.0.0.1:{DEMO_PORT} - use the frontend as usual. "
              "Ctrl+C to stop.")
        try:
            uvicorn.run("app.main:app", host="127.0.0.1", port=DEMO_PORT)
        except KeyboardInterrupt:   # uvicorn re-raises Ctrl+C once it has shut down cleanly
            pass


def cleanup() -> None:
    with _demo_lock():
        _tidy_leftovers()
        removed = _delete_folder(DEMO_DIR)
    if os.path.isfile(LEGACY_STATE):
        os.remove(LEGACY_STATE)
    print(f"Deleted the demo copy ({DEMO_DIR})." if removed else "There's no demo copy to delete.")
    if _has_legacy_demo(_database_file()):
        print("\n" + LEGACY_HELP)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plant-only", action="store_true",
                       help="plant the scenario but leave the pipeline to the UI")
    group.add_argument("--serve", action="store_true",
                       help="run the backend on the demo copy (stop the normal one first)")
    group.add_argument("--cleanup", action="store_true", help="delete the demo copy")
    args = parser.parse_args()

    if args.cleanup:
        cleanup()
    elif args.serve:
        serve()
    else:
        build(args.plant_only)


if __name__ == "__main__":
    main()
