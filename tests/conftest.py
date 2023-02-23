"""Configuration for the pytest test suite."""
import os
import re
import sys
from copy import deepcopy

import pytest
import responses
from pdm.cli.actions import do_init
from pdm.core import Core
from pdm.project import Config, Project

pytest_plugins = "pdm.pytest"

PYTHON_VERSION = sys.version.split(" ")[0]
REPO_BASE = "https://anaconda.org"
PYTHON_REQUIREMENTS = [
    {
        "name": "lib2",
        "depends": [],
        "version": "1.0.0g",
        "build_number": 0,
        "url": f"{REPO_BASE}/channel/lib2",
        "channel": f"{REPO_BASE}/channel",
        "sha256": "this-is-a-hash",
        "build_string": "lib2",
    },
    {
        "name": "openssl",
        "depends": [],
        "version": "1.1.1s",
        "build_number": 0,
        "url": f"{REPO_BASE}/channel/lib2",
        "channel": f"{REPO_BASE}/channel",
        "sha256": "this-is-a-hash",
        "build_string": "lib2",
    },
    {
        "name": "lib",
        "depends": ["lib2 ==1.0.0g", "openssl >=1.1.1s,<1.1.2a"],
        "version": "1.0.0",
        "build_number": 0,
        "url": f"{REPO_BASE}/channel/lib",
        "channel": f"{REPO_BASE}/channel",
        "sha256": "this-is-a-hash",
        "build_string": "lib",
    },
    {
        "name": "python",
        "depends": ["lib ==1.0.0"],
        "build_number": 0,
        "version": PYTHON_VERSION,
        "url": f"{REPO_BASE}/channel/python",
        "channel": f"{REPO_BASE}/channel",
        "sha256": "this-is-a-hash",
        "build_string": "python",
    },
]
PYTHON_PACKAGE = PYTHON_REQUIREMENTS[-1]
CONDA_INFO = [
    [
        *PYTHON_REQUIREMENTS,
        {
            "name": "another-dep",
            "depends": [],
            "version": "1!0.0gg",
            "build_number": 0,
            "url": f"{REPO_BASE}/channel/another-dep",
            "channel": f"{REPO_BASE}/channel",
            "sha256": "this-is-a-hash",
            "build_string": "another-dep",
        },
        {
            "name": "another-dep",
            "depends": [],
            "build_number": 1,
            "version": "1!0.0gg",
            "url": f"{REPO_BASE}/channel/another-dep",
            "channel": f"{REPO_BASE}/channel",
            "sha256": "this-is-a-hash",
            "build_string": "another-dep",
        },
        {
            "name": "dep",
            "build_number": 0,
            "depends": ["python >=3.7", "another-dep ==1!0.0gg|==1!0.0g"],
            "version": "1.0.0",
            "url": f"{REPO_BASE}/channel/dep",
            "channel": f"{REPO_BASE}/channel",
            "sha256": "this-is-a-hash",
            "build_string": "dep",
        },
    ],
]

CONDA_MAPPING = [{f"{p['name']}-pip": p["name"] for p in CONDA_INFO[0] if p not in PYTHON_REQUIREMENTS}]


@pytest.fixture(name="core")
def core_with_plugin(core, monkeypatch) -> Core:
    from pdm_conda import main

    Config._config_map["python.use_venv"].default = True
    monkeypatch.setenv("_CONDA_PREFIX", os.getenv("CONDA_PREFIX"))
    main(core)
    yield core


@pytest.fixture
def distributions(mocker):
    mocker.patch("pdm.models.working_set.distributions", return_value=[])


@pytest.fixture
def project(core, project_no_init, monkeypatch) -> Project:
    _project = project_no_init
    _project.global_config["check_update"] = False
    _project.global_config["pypi.json_api"] = True
    _project.global_config["pypi.url"] = REPO_BASE
    do_init(
        _project,
        name="test",
        version="0.0.0",
        python_requires=f"=={PYTHON_VERSION}",
        author="test",
        email="test@test.com",
    )
    monkeypatch.setenv("CONDA_PREFIX", os.getenv("_CONDA_PREFIX"))
    yield _project


@pytest.fixture(name="pdm")
def pdm_run(core, pdm):
    yield pdm


@pytest.fixture(name="conda")
def mock_conda(mocker, conda_response: dict | list, empty_conda_list: bool = False):
    if isinstance(conda_response, dict):
        conda_response = [conda_response]
    install_response = {
        "actions": {
            "LINK": conda_response,
        },
    }

    def _mock(cmd, **kwargs):
        subcommand = cmd[1]
        if subcommand == "install":
            return deepcopy(install_response)
        elif subcommand == "list":
            python_packages = {p["name"] for p in PYTHON_REQUIREMENTS}
            res = []
            listed_packages = set()
            for p in conda_response:
                if p["name"] not in listed_packages:
                    listed_packages.add(p["name"])
                    res.append(deepcopy(p))
            if empty_conda_list:
                res = [c for c in res if c["name"] in python_packages]
            for p in res:
                if p["channel"].startswith("http"):
                    p["channel"] = p["channel"].split("/")[-1]
            return res
        elif subcommand == "info":
            return {
                "virtual packages": [
                    "__unix=0=0",
                    "__linux=5.10.109=0",
                    "__glibc=2.35=0",
                    "__archspec=1=aarch64",
                ],
            }
        elif subcommand == "search":
            name = next(filter(lambda x: not x.startswith("-"), cmd[2:]))
            name = name.split(">")[0].split("<")[0].split("=")[0].split("~")[0]
            return {"result": {"pkgs": [deepcopy(p) for p in conda_response if p["name"] == name]}}
        else:
            return {"message": "ok"}

    yield mocker.patch("pdm_conda.plugin.run_conda", side_effect=_mock)


@pytest.fixture(name="pypi")
def mock_pypi(mocked_responses):
    def _mocker(conda_response, with_dependencies: list[str] | None = None):
        if with_dependencies is None:
            with_dependencies = []
        for package in conda_response:
            dependencies = list(package["depends"])
            requires_python = ""
            to_delete = []
            for d in dependencies:
                if d.startswith("__"):
                    to_delete.append(d)
                elif d.startswith("python "):
                    to_delete.append(d)
                    if not requires_python:
                        requires_python = d.split(" ")[-1]
            for d in to_delete:
                dependencies.remove(d)
            name = package["name"]
            version = package["version"]
            mocked_responses.get(
                f"{REPO_BASE}/{name}/",
                content_type="application/vnd.pypi.simple.v1+json",
                json=dict(
                    files=[
                        {
                            "url": f"{name}#egg={name}-{re.sub('[a-z]', '', version)}",
                            "requires-python": requires_python,
                            "yanked": None,
                            "dist-info-metadata": False,
                            "hashes": None,
                        },
                    ],
                ),
            )

            if name in with_dependencies:
                mocked_responses.get(
                    f"{REPO_BASE}/pypi/{name}/{version}/json",
                    json=dict(
                        info=dict(
                            summary="",
                            requires_python=requires_python,
                            requires=[d.split("|")[0] for d in dependencies],
                        ),
                    ),
                )

    return _mocker


@pytest.fixture
def mocked_responses():
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def mock_conda_mapping(mocker, mocked_responses, conda_mapping):
    yield mocker.patch("pdm_conda.mapping.download_mapping", return_value=conda_mapping)
    from pdm_conda.mapping import get_pypi_mapping

    get_pypi_mapping.cache_clear()
