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
def project(core) -> Project:
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
def mock_conda(mocker, conda_response: dict | list):
    if isinstance(conda_response, dict):
        conda_response = [conda_response]
    install_response = {
        "actions": {
            "LINK": conda_response,
        },
    }

    def _mock(cmd, **kwargs):
        if cmd[1] == "install":
            return install_response
        else:
            return {"message": "ok"}

    yield mocker.patch("pdm_conda.plugin.run_conda", side_effect=_mock)


CONDA_INFO = [
    [
        {
            "name": "pdm",
            "depends": ["python >=3.7", "another-pdm ==1.0.0"],
            "version": "1.0.0",
            "url": "https://channel.com/package",
            "channel": "https://channel.com",
            "sha256": "this-is-a-hash",
        },
        {
            "name": "another-pdm",
            "depends": [],
            "version": "1.0.0",
            "url": "https://channel.com/package",
            "channel": "https://channel.com",
            "sha256": "this-is-a-hash",
        },
    ],
]
