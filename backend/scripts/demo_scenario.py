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
--cleanup refuse to start. Planting again replaces the copy with a fresh copy
of your current data; if that fails or is interrupted, --serve refuses the
unfinished copy until you plant again.

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

# Only app.config at import time: anything that imports app.database (app.models,
# app.ml, app.main) must wait until point_app_at() has run - see its docstring.
from app.config import BACKEND_DIR, settings
from scripts.demo_common import (DATABASE_NAME, DEMO_DIR, PREFIX, PREFIX_END, READY_FILE,
                                 database_file, demo_settings, point_app_at)

DEMO_PORT = 8000                                            # where the frontend's VITE_API_URL points
COPY_TIMEOUT = 60                                           # seconds to wait for a locked database
LOCK_FILE = os.path.join(BACKEND_DIR, "data", "demo.lock")  # held while a demo command runs (gitignored)
DEMO_BUSY = ("The demo copy is in use: stop the demo backend (--serve), or wait for the other "
             "demo command to finish.")

if os.name == "nt":
    import msvcrt

    def _try_lock(fh):   # raises OSError if it can't
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh):
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fh):   # raises OSError if it can't
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh):
        fcntl.flock(fh, fcntl.LOCK_UN)

# Older versions of this script planted into the real data
LEGACY_SNAPSHOT_DIR = os.path.join(BACKEND_DIR, "data", "demo_snapshot")
LEGACY_STATE = settings.saved_model_file("demo_state.json")
LEGACY_HELP = """\
An older version of this script planted the demo into your real data (DEMO- rows
in the database, or a data/demo_snapshot/ folder). Undo it with that version's
own cleanup, from the backend/ folder:
  git restore --source d3dbd1b scripts/demo_scenario.py
  python -m scripts.demo_scenario --cleanup
  git restore scripts/demo_scenario.py"""


# ------------------------------------------------------------- the real data

def _inside_demo(path: str) -> bool:
    """Whether path is in the demo folder, also when reached through a symlink,
    junction or subst drive."""
    real = os.path.normcase(os.path.realpath(path))
    return real.startswith(os.path.normcase(os.path.realpath(DEMO_DIR)) + os.sep)


def _source_database() -> str:
    """The real database file to copy, once it's clear that neither it nor the
    pipeline outputs are inside the demo folder (which a build deletes)."""
    path = database_file(settings.DATABASE_URL)
    if path is None:
        raise SystemExit("The demo copies the database file, so it needs a SQLite DATABASE_URL.")
    if not os.path.isfile(path):
        raise SystemExit(f"No database at {path}. Set it up first:\n  python -m scripts.init_db\n"
                         "  python -m data.generate_synthetic\n  python -m scripts.seed_data")
    for setting, value in (("DATABASE_URL", path), ("PIPELINE_OUTPUT_DIR", settings.saved_models_dir)):
        if _inside_demo(value):
            raise SystemExit(f"{setting} points into {DEMO_DIR}, the demo copy. Unset it first.")
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


def _retrying(action, *args, attempts: int = 5):
    """action(*args), retried for a couple of seconds while a file is in use: on
    Windows a virus scanner or the search indexer can briefly hold files that
    were just written."""
    for attempt in range(attempts):
        try:
            return action(*args)
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.5)


def _delete_demo() -> bool:
    """Delete the demo copy, its ready marker first: if deleting the rest stops
    partway, what's left can't be served."""
    if not os.path.exists(DEMO_DIR):
        return False
    try:
        if os.path.exists(READY_FILE):
            _retrying(os.remove, READY_FILE)
        _retrying(shutil.rmtree, DEMO_DIR)
    except OSError as exc:
        raise SystemExit(f"Couldn't delete {exc.filename or DEMO_DIR}: {exc.strerror or exc}. "
                         "Close any program using the demo's files and try again.") from None
    return True


def _copy_real_data(source: str, folder: str) -> None:
    """Copy the database and pipeline outputs into folder. Only reads the originals."""
    target = demo_settings(folder)
    os.makedirs(target.saved_models_dir)
    os.makedirs(target.processed_dir)
    _sqlite_copy(source, os.path.join(folder, DATABASE_NAME))
    if os.path.isdir(settings.saved_models_dir):
        for name in os.listdir(settings.saved_models_dir):
            path = settings.saved_model_file(name)
            if os.path.isfile(path):
                shutil.copy2(path, target.saved_models_dir)
    if os.path.isfile(settings.features_csv):
        shutil.copy2(settings.features_csv, target.processed_dir)
    print("Copied your database and pipeline outputs.")


# ---------------------------------------------------------------- the commands

@contextmanager
def _demo_lock():
    """One demo command at a time: --serve holds this for as long as the demo
    backend runs, so planting or cleaning up can't delete the copy out from
    under it. The OS releases the lock when the process ends, however it ends."""
    with open(LOCK_FILE, "a") as fh:
        try:
            _try_lock(fh)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):   # another process holds it
                raise SystemExit(DEMO_BUSY) from None
            raise SystemExit(f"Couldn't lock {LOCK_FILE}: {exc.strerror}") from None
        try:
            yield
        finally:
            _unlock(fh)


def build(plant_only: bool) -> None:
    """Replace the demo copy with a fresh copy of the real data, plant the
    scenario into it and, unless plant_only, run the pipeline there. The copy
    is marked ready only at the end, so --serve refuses one whose build failed
    or was interrupted."""
    source = _source_database()
    if _has_legacy_demo(source):
        raise SystemExit(LEGACY_HELP)
    with _demo_lock():
        _delete_demo()
        _copy_real_data(source, DEMO_DIR)
        point_app_at(DEMO_DIR)   # from here on, this process only sees the copy
        from scripts import demo_plant   # the ML stack: imported only now that it's needed

        demo_plant.run(plant_only)
        with open(READY_FILE, "w") as fh:
            fh.write("The demo build finished; --serve only serves a copy that has this file.\n")

    if plant_only:
        print("\nNow stop your normal backend, start the demo one with\n"
              "  python -m scripts.demo_scenario --serve\nthen log in and run, in the "
              "sidebar's order: Rule Detection -> Graph Analysis -> Features -> ML Scoring "
              f"-> Fraud Alerts -> Fraud Rings.\nThen search for {PREFIX} on the Accounts, "
              "Alerts and Fraud Rings pages.")
    else:
        print("\nTo show it in the UI, stop your normal backend and run\n"
              "  python -m scripts.demo_scenario --serve\n"
              f"then search for {PREFIX} on Accounts / Alerts, or open the ring on Fraud Rings.")
        print("Your own database and pipeline outputs were not changed. "
              "Delete the copy with --cleanup.")


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
        if not os.path.isfile(READY_FILE):
            command = "python -m scripts.demo_scenario"
            raise SystemExit(f"The last demo build didn't finish. Build it again: {command}"
                             if os.path.exists(DEMO_DIR) else
                             f"There's no demo copy yet. Make one first: {command}")
        if _port_in_use(DEMO_PORT):
            raise SystemExit(f"Port {DEMO_PORT} is in use. Stop your normal backend "
                             "(Ctrl+C in its terminal) and try again.")
        point_app_at(DEMO_DIR)
        import uvicorn   # only --serve needs it

        print(f"Serving the demo copy on http://127.0.0.1:{DEMO_PORT} - use the frontend as usual. "
              "Ctrl+C to stop.")
        try:
            uvicorn.run("app.main:app", host="127.0.0.1", port=DEMO_PORT)
        except KeyboardInterrupt:   # uvicorn re-raises Ctrl+C once it has shut down cleanly
            pass


def cleanup() -> None:
    with _demo_lock():
        removed = _delete_demo()
    if os.path.isfile(LEGACY_STATE):
        os.remove(LEGACY_STATE)
    print(f"Deleted the demo copy ({DEMO_DIR})." if removed else "There's no demo copy to delete.")
    if _has_legacy_demo(database_file(settings.DATABASE_URL)):
        print("\n" + LEGACY_HELP)


def main():
    for stream in (sys.stdout, sys.stderr):   # errors name folders too
        if hasattr(stream, "reconfigure"):   # not under pythonw or some IDE runners
            stream.reconfigure(encoding="utf-8")   # rule labels and folder names cp1252 can't print
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
