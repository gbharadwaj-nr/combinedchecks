"""Client configuration loader for the Daily Health Check framework.

Configuration lives under clients/<client>.yaml, layered on top of
clients/_defaults.yaml. Client-specific values (AWS account/role, regions,
tag filters, URLs, log groups, thresholds, batch names, etc.) always live in
these YAML files - never hardcoded in check modules.
"""
import copy
import os

import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENTS_DIR = os.path.join(BASE_DIR, "clients")
DEFAULTS_FILE = os.path.join(CLIENTS_DIR, "_defaults.yaml")


class ConfigError(Exception):
    """Raised when a client's configuration is missing or invalid."""


def _load_yaml(path):
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _deep_merge(base, override):
    """Recursively merge `override` onto `base`, returning a new dict."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ClientConfig:
    """Wraps the merged (defaults + client) configuration with convenience accessors."""

    def __init__(self, client_name, data):
        self.client_name = client_name
        self._data = data

    def get(self, *path, default=None):
        node = self._data
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def section(self, name):
        """Return the raw dict for a top-level section (e.g. 'rds', 'kafka')."""
        return self._data.setdefault(name, {})

    @property
    def raw(self):
        return self._data


def load_client_config(client_name):
    client_file = os.path.join(CLIENTS_DIR, f"{client_name.lower()}.yaml")
    if not os.path.isfile(client_file):
        raise ConfigError(f"No configuration found for client '{client_name}' (expected {client_file})")

    defaults = _load_yaml(DEFAULTS_FILE)
    client_data = _load_yaml(client_file)
    merged = _deep_merge(defaults, client_data)
    return ClientConfig(client_name.upper(), merged)


def list_available_clients():
    if not os.path.isdir(CLIENTS_DIR):
        return []
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(CLIENTS_DIR)
        if f.endswith(".yaml") and not f.startswith("_")
    )
