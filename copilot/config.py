"""Load the YAML configuration. Full validation of metrics and thresholds arrives in Step 3."""
import pathlib

import yaml

CONFIG = pathlib.Path(__file__).resolve().parent.parent / "config"

QUARTERS = ("Q4FY25", "Q1FY26", "Q3FY26", "Q4FY26", "Q1FY27")
TARGET_QUARTERS = ("Q4FY26", "Q1FY27")


class ConfigError(Exception):
    pass


def load(name):
    path = CONFIG / name
    if not path.exists():
        raise ConfigError(f"missing config file: {path}")
    return yaml.safe_load(path.read_text(encoding="utf8"))


def companies():
    rows = load("companies.yaml")["companies"]
    ids = [c["id"] for c in rows]
    if len(ids) != len(set(ids)):
        raise ConfigError("duplicate company id in companies.yaml")
    return {c["id"]: c for c in rows}
