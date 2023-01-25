"""Configuration for the pytest test suite."""
import sys
from copy import deepcopy
from tempfile import TemporaryDirectory

import pytest
import responses
from pdm.cli.actions import do_init
from pdm.core import Core
from pdm.project import Project

from pdm_conda import main


@pytest.fixture(scope="session")
def core() -> Core:
    _core = Core()
    main(_core)
    yield _core


@pytest.fixture
def distributions(mocker):
    mocker.patch("pdm.models.working_set.distributions", return_value=[])


@pytest.fixture
def project(core, distributions) -> Project:
    with TemporaryDirectory() as tmp_dir:
        _project = core.create_project(tmp_dir)
        do_init(
            _project,
            name="test",
            version="0.0.0",
            python_requires=f"=={PYTHON_VERSION}",
            author="test",
            email="test@test.com",
        )
        _project.global_config["check_update"] = False
        yield _project


@pytest.fixture
def mock_conda(mocker, conda_response: dict | list, empty_conda_list):
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


@pytest.fixture
def mocked_responses():
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def mock_conda_mapping(mocker, mocked_responses, conda_mapping):
    yield mocker.patch("pdm_conda.mapping.download_mapping", return_value=conda_mapping)
    from pdm_conda.mapping import get_pypi_mapping

    get_pypi_mapping.cache_clear()


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
        "name": "lib",
        "depends": ["lib2 ==1.0.0g"],
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
