"""The pipeline's files in saved_models/ (PIPELINE_OUTPUT_DIR in config can move them)."""
import json
import os

from app.config import settings


def output_path(name: str) -> str:
    """Where to write a file in saved_models/; creates the folder if needed."""
    os.makedirs(settings.saved_models_dir, exist_ok=True)
    return settings.saved_model_file(name)


def save_json(name: str, data, **dump_options) -> None:
    with open(output_path(name), "w") as fh:
        json.dump(data, fh, **dump_options)


def load_json(name: str):
    """The saved file's contents, or None if it hasn't been written yet."""
    try:
        with open(settings.saved_model_file(name)) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
