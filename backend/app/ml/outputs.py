"""The pipeline's output files: saved_models/ and processed/features.csv
(PIPELINE_OUTPUT_DIR in config can move them)."""
import json
import os
import time
import uuid
from contextlib import contextmanager

from app.config import settings


def output_path(name: str) -> str:
    """Where to write a file in saved_models/; creates the folder if needed."""
    os.makedirs(settings.saved_models_dir, exist_ok=True)
    return settings.saved_model_file(name)


def _when_free(action, *args, attempts: int = 20):
    """action(*args), retried for up to two seconds on PermissionError: on
    Windows a file can't be replaced while a request is reading it, nor opened
    in the instant it's being replaced."""
    for attempt in range(attempts):
        try:
            return action(*args)
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.1)


@contextmanager
def replacing(path: str):
    """Write to the temporary path this yields; when the block ends, it replaces
    path in one step. A page reading path meanwhile gets the old file or the new
    one, never half of one, and a write that fails leaves the old file as it was."""
    tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"   # unique: two requests may write the same file at once
    try:
        yield tmp
        _when_free(os.replace, tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_file(path: str, read):
    """read(path), or None if the file hasn't been written yet."""
    try:
        return _when_free(read, path)
    except FileNotFoundError:
        return None


def save_json(name: str, data, **dump_options) -> None:
    with replacing(output_path(name)) as tmp, open(tmp, "w") as fh:
        json.dump(data, fh, **dump_options)


def _read_json(path: str):
    with open(path) as fh:
        return json.load(fh)


def load_json(name: str):
    """The saved file's contents, or None if it hasn't been written yet."""
    return read_file(settings.saved_model_file(name), _read_json)
