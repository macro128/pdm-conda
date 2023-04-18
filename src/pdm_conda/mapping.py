import json
import os
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import requests

MAPPINGS_URL = "https://github.com/regro/cf-graph-countyfair/raw/master/mappings/pypi/grayskull_pypi_mapping.yaml"
DOWNLOAD_DIR_ENV_VAR = "PYPI_MAPPING_DIR"


def process_mapping(yaml_path: Path, dict_path: Path):
    """
    Create json mapping from yaml mapping
    :param yaml_path: yaml path
    :param dict_path: json path
    """

    def find_key(key, f):
        while line := f.readline():
            line = line.strip()
            if line.startswith(key):
                return line.split(key)[-1].strip()
        return None

    mappings = dict()
    with yaml_path.open() as f:
        while (conda_name := find_key("conda_name:", f)) is not None:
            pypi_name = find_key("pypi_name:", f)
            if pypi_name:
                mappings[pypi_name] = conda_name

    with dict_path.open("w") as f:
        json.dump(mappings, f)


def download_mapping(download_dir: Path, update_interval: timedelta | None = None) -> dict[str, str]:
    """
    Download and process Conda-PyPI mapping from GitHub
    :param download_dir: download dir
    :param update_interval: update interval, if mapping file modified date is greater than update interval the reload
    :return: Conda mapping
    """
    if update_interval is None:
        update_interval = timedelta(days=15)
    download_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = download_dir / "pypi_mapping.yaml"
    dict_path = yaml_path.with_suffix(".json")

    if not yaml_path.exists() or datetime.fromtimestamp(yaml_path.stat().st_mtime) + update_interval < datetime.now():
        response = requests.get(MAPPINGS_URL, stream=True)
        with yaml_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=128):
                f.write(chunk)
        process_mapping(yaml_path, dict_path)

    with dict_path.open() as f:
        return json.load(f)


@lru_cache
def get_pypi_mapping() -> dict[str, str]:
    download_dir = os.getenv(DOWNLOAD_DIR_ENV_VAR)
    return download_mapping(Path(str(download_dir)))


@lru_cache
def get_conda_mapping() -> dict[str, str]:
    return {v: k for k, v in get_pypi_mapping().items()}


def _requirement_map(requirement: str, mapping: dict):
    requirement = requirement.strip()
    name = requirement
    for s in (">", "<", "=", "!", "~", " ", "["):
        name = name.split(s, maxsplit=1)[0]
    name = name.split("::")[-1].strip()
    return mapping.get(name, name)


def pypi_to_conda(requirement: str) -> str:
    """
    Map PyPI requirement to Conda version
    :param requirement: PyPI requirement
    :return: Conda requirement
    """
    return _requirement_map(requirement, get_pypi_mapping()).lower()


def conda_to_pypi(requirement: str) -> str:
    """
    Map Conda requirement to PyPI version
    :param requirement: Conda requirement
    :return: PyPI requirement
    """
    return _requirement_map(requirement, get_conda_mapping())
