"""Configuration for the pytest test suite."""
from tempfile import TemporaryDirectory

import pytest
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
            python_requires=">=3.10",
            author="test",
            email="test@test.com",
        )
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
            return install_response
        elif subcommand == "list":
            if empty_conda_list:
                return []
            return conda_response
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
            return {"result": {"pkgs": [p for p in conda_response if p["name"] == name]}}
        else:
            return {"message": "ok"}

    yield mocker.patch("pdm_conda.plugin.run_conda", side_effect=_mock)


PYTHON_REQUIREMENTS = [
    {
        "name": "lib2",
        "depends": [],
        "version": "1.0.0",
        "url": "https://channel.com/lib2",
        "channel": "https://channel.com",
        "sha256": "this-is-a-hash",
        "build_string": "lib2",
    },
    {
        "name": "lib",
        "depends": ["lib2 ==1.0.0"],
        "version": "1.0.0",
        "url": "https://channel.com/lib",
        "channel": "https://channel.com",
        "sha256": "this-is-a-hash",
        "build_string": "lib",
    },
    {
        "name": "python",
        "depends": ["lib ==1.0.0"],
        "version": "3.10.9",
        "url": "https://channel.com/python",
        "channel": "https://channel.com",
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
            "version": "1.0.0",
            "url": "https://channel.com/another-dep",
            "channel": "https://channel.com",
            "sha256": "this-is-a-hash",
            "build_string": "another-dep",
        },
        {
            "name": "dep",
            "depends": ["python >=3.7", "another-dep ==1.0.0"],
            "version": "1.0.0",
            "url": "https://channel.com/dep",
            "channel": "https://channel.com",
            "sha256": "this-is-a-hash",
            "build_string": "dep",
        },
    ],
]
