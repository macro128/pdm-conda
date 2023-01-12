import json
from datetime import datetime, timedelta
from pathlib import Path

import requests

MAPPINGS_URL = "https://github.com/regro/cf-graph-countyfair/raw/master/mappings/pypi/grayskull_pypi_mapping.yaml"


def process_mapping(yaml_path: Path, dict_path: Path):
    """
    Create json mapping from yaml mapping
    :param yaml_path: yaml path
    :param dict_path: json path
    """
    mappings = dict()
    conda_key = "conda_name:"
    pypi_key = "pypi_name:"
    with yaml_path.open() as f:
        while line := f.readline():
            line = line.strip()
            if line.startswith(conda_key):
                conda_name = line.split(conda_key)[-1].strip()
                pypi_name = None
                while line := f.readline():
                    if line.startswith(pypi_key):
                        pypi_name = line.split(pypi_key)[-1].strip()
                        break
                if pypi_name:
                    mappings[conda_name] = pypi_name
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

    if (
        not yaml_path.exists()
        or datetime.fromtimestamp(yaml_path.stat().st_mtime) + update_interval > datetime.utcnow()
    ):
        response = requests.get(MAPPINGS_URL, stream=True)
        with yaml_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=128):
                f.write(chunk)
        process_mapping(yaml_path, dict_path)

    with dict_path.open() as f:
        return json.load(f)
