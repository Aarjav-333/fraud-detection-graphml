"""What scripts/demo_scenario.py and scripts/demo_plant.py share: the demo's
ids and folders, and pointing the app at a demo database."""
import os
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

# Only app.config at import time: anything that imports app.database (app.models,
# app.ml, app.main) must wait until point_app_at() has run - see its docstring.
# (app.demo.scenario is pure data and imports nothing from the app.)
from app.config import BACKEND_DIR, settings
from app.demo.scenario import PREFIX, PREFIX_END  # noqa: F401  (re-exported for the demo scripts)

DEMO_DIR = os.path.join(BACKEND_DIR, "data", "demo")   # the copy of the real data (gitignored)
READY_FILE = os.path.join(DEMO_DIR, "ready.txt")       # written last, once the copy is finished
# Only the scripted scenario, in a database of its own (gitignored)
STANDALONE_DIR = os.path.join(BACKEND_DIR, "data", "demo_standalone")
DATABASE_NAME = "fraud_detection.db"


def database_file(url) -> str | None:
    """The absolute SQLite file a database URL names, or None for any other database."""
    url = make_url(url)
    if url.get_backend_name() != "sqlite" or url.database in (None, "", ":memory:"):
        return None
    return os.path.abspath(url.database)


def demo_settings(folder: str):
    """The app's settings when pointed at a demo folder."""
    return settings.model_copy(update={
        "DATABASE_URL": "sqlite:///" + Path(folder, DATABASE_NAME).as_posix(),
        "PIPELINE_OUTPUT_DIR": folder,
    })


def _check_database(folder: str, engine) -> None:
    expected = os.path.join(folder, DATABASE_NAME)
    actual = database_file(engine.url)
    if actual is None or os.path.normcase(actual) != os.path.normcase(expected):
        raise SystemExit(f"The app's database is {actual or engine.url}, not the demo database {expected}.")


def check_pointed_at(folder: str, engine) -> None:
    """Refuse to go on unless the app's database and pipeline outputs are the copy in folder."""
    _check_database(folder, engine)
    target = demo_settings(folder)
    for actual, expected in ((settings.saved_models_dir, target.saved_models_dir),
                             (settings.processed_dir, target.processed_dir)):
        if actual != expected:
            raise SystemExit(f"The app's pipeline outputs go to {actual}, not the demo's {expected}.")


def point_app_at(folder: str, demo_mode: str = ""):
    """Point the app at the copy in folder for the rest of this process and
    return its database engine. app.database builds its engine from
    DATABASE_URL when first imported, so this sets the URL first: the engine,
    and every session from it, then use the copy - nothing in this process
    can reach the real database through the app."""
    if "app.database" in sys.modules:
        raise RuntimeError(
            "app.database was imported before point_app_at(), so its engine points at the real "
            "database. In the demo scripts, import modules that use the database (app.database, "
            "app.models, app.ml, app.main) only after point_app_at() has run.")
    target = demo_settings(folder)
    settings.DATABASE_URL = target.DATABASE_URL
    settings.PIPELINE_OUTPUT_DIR = target.PIPELINE_OUTPUT_DIR
    settings.DEMO_MODE = demo_mode   # "standalone": the app shows it, and turns ML/GNN training off
    from app.database import engine   # imported here on purpose: it must come after the lines above

    _check_database(folder, engine)
    return engine
