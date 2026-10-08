"""What scripts/demo_scenario.py and scripts/demo_plant.py share: the demo's
ids and folders, and pointing the app at a demo copy."""
import os
import sys
from pathlib import Path

from app.config import BACKEND_DIR, settings

PREFIX = "DEMO-"
# Upper bound for a case-sensitive prefix match that can still use the uid
# indexes: uid >= PREFIX and uid < PREFIX_END. Not LIKE 'DEMO-%': SQLite's LIKE
# ignores case, so it would also match a real account named "demo-...".
PREFIX_END = PREFIX[:-1] + chr(ord(PREFIX[-1]) + 1)   # "DEMO."

DEMO_DIR = os.path.join(BACKEND_DIR, "data", "demo")        # the finished copy (gitignored)
BUILD_DIR = os.path.join(BACKEND_DIR, "data", "demo.new")   # the copy being built (gitignored)
OLD_DIR = os.path.join(BACKEND_DIR, "data", "demo.old")     # the previous copy, mid-swap (gitignored)
DATABASE_NAME = "fraud_detection.db"


def demo_settings(folder: str):
    """The app's settings when pointed at a demo folder."""
    return settings.model_copy(update={
        "DATABASE_URL": "sqlite:///" + Path(folder, DATABASE_NAME).as_posix(),
        "PIPELINE_OUTPUT_DIR": folder,
    })


def check_pointed_at(folder: str, engine) -> None:
    """Refuse to go on unless the app's database and pipeline outputs are the copy in folder."""
    expected = demo_settings(folder)
    database = os.path.normcase(os.path.abspath(engine.url.database or ""))
    if (database != os.path.normcase(os.path.join(folder, DATABASE_NAME))
            or settings.saved_models_dir != expected.saved_models_dir
            or settings.processed_dir != expected.processed_dir):
        raise SystemExit(f"The app isn't pointed at the demo copy in {folder}. "
                         "Use: python -m scripts.demo_scenario")


def point_app_at(folder: str):
    """Point the app at the copy in folder for the rest of this process and
    return its database engine. app.database builds its engine from
    DATABASE_URL when first imported, so this sets the URL first: the engine,
    and every session from it, then use the copy - nothing in this process
    can reach the real database through the app."""
    if "app.database" in sys.modules:
        raise RuntimeError("app.database was imported before the app was pointed at the demo copy")
    target = demo_settings(folder)
    settings.DATABASE_URL = target.DATABASE_URL
    settings.PIPELINE_OUTPUT_DIR = target.PIPELINE_OUTPUT_DIR
    from app.database import engine   # imported here on purpose: it must come after the lines above

    check_pointed_at(folder, engine)
    return engine
