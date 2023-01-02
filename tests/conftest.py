"""Configuration for the pytest test suite."""
from tempfile import TemporaryDirectory

import pytest
from pdm.cli.actions import do_init
from pdm.core import Core
from pdm.project import Project

from pdm_conda import main


@pytest.fixture
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
