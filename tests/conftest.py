"""Configuration for the pytest test suite."""
import os
import sys
from copy import deepcopy

import pytest
import responses
from pdm.cli.actions import do_init
from pdm.core import Core
from pdm.models.backends import PDMBackend
from pdm.project import Config, Project
from pytest_mock import MockerFixture

from tests.utils import (
    DEFAULT_CHANNEL,
    PLATFORM,
    REPO_BASE,
    channel_url,
    generate_package_info,
)

pytest_plugins = "pdm.pytest"

PYTHON_VERSION = sys.version.split(" ")[0]

PYTHON_PACKAGE = generate_package_info("python", PYTHON_VERSION, ["lib 1.0"])
PYTHON_REQUIREMENTS = [
    generate_package_info("openssl", "1.1.1a"),
    generate_package_info("openssl", "1.1.1c"),
    PYTHON_PACKAGE,
]

PREFERRED_VERSIONS = dict(python=PYTHON_PACKAGE)
_packages = [
    generate_package_info("openssl", "1.1.1b"),
    generate_package_info("lib2", "1.0.0g"),
    generate_package_info("lib", "1.0", ["lib2 ==1.0.0g", "openssl >=1.1.1c,<1.1.2a"]),
]
for _p in _packages:
    PREFERRED_VERSIONS[_p["name"]] = _p
    PYTHON_REQUIREMENTS.append(_p)
PYTHON_REQUIREMENTS.extend(PREFERRED_VERSIONS.values())

_CONDA_INFO = [
    *PYTHON_REQUIREMENTS,
    generate_package_info("another-dep", "1!0.0gg"),
    generate_package_info("another-dep", "1!0.1gg", timestamp=3),
    generate_package_info("another-dep", "1!0.1gg", build_number=1, timestamp=4, channel=f"{DEFAULT_CHANNEL}/noarch"),
    generate_package_info("another-dep", "1!0.1gg", timestamp=1),
]

_packages = [
    generate_package_info("another-dep", "1!0.1gg", timestamp=2, build_number=1),
    generate_package_info(
        "dep",
        "1.0.0",
        depends=[f"python >={PYTHON_VERSION}", "another-dep ==1!0.1gg|==1!0.0g"],
        timestamp=2,
        build_number=1,
    ),
]
for _p in _packages:
    PREFERRED_VERSIONS[_p["name"]] = _p
    _CONDA_INFO.append(_p)

CONDA_MAPPING = [{f"{p['name']}-pip": p["name"] for p in _CONDA_INFO}]
CONDA_INFO = [[*PYTHON_REQUIREMENTS, *_CONDA_INFO]]
BUILD_BACKEND = generate_package_info("pdm-backend", "2.0")


@pytest.fixture(autouse=True, name="test_name")
def _test_name():
    yield os.getenv("PYTEST_CURRENT_TEST").split(":")[-1]


@pytest.fixture(name="test_id")
def _test_id(test_name):
    yield test_name.split("[")[-1].split("]")[0]


@pytest.fixture(name="core")
def core_with_plugin(core, monkeypatch) -> Core:
    from pdm_conda import main

    Config._config_map["python.use_venv"].default = True
    monkeypatch.setenv("_CONDA_PREFIX", os.getenv("CONDA_PREFIX"))
    main(core)
    yield core


@pytest.fixture
def project(core, project_no_init, monkeypatch) -> Project:
    _project = project_no_init
    _project.global_config["check_update"] = False
    _project.global_config["pypi.json_api"] = True
    _project.global_config["pypi.url"] = f"{REPO_BASE}/simple"
    do_init(
        _project,
        name="test",
        version="0.0.0",
        python_requires=f"=={PYTHON_VERSION}",
        author="test",
        email="test@test.com",
        build_backend=PDMBackend,
    )
    monkeypatch.setenv("CONDA_PREFIX", os.getenv("_CONDA_PREFIX"))
    yield _project


@pytest.fixture(name="pdm")
def pdm_run(core, pdm):
    yield pdm


@pytest.fixture(name="conda")
def mock_conda(mocker: MockerFixture, conda_info: dict | list, installed_packages):
    if isinstance(conda_info, dict):
        conda_info = [conda_info]
    install_response = {
        "actions": {
            "LINK": conda_info,
        },
    }

    def _mock(cmd, **kwargs):
        runner, subcommand, *_ = cmd
        if subcommand == "install":
            for url in kwargs.get("dependencies", []):
                installed_packages.extend(
                    [p for p in PREFERRED_VERSIONS.values() if url.startswith(p["url"])],
                )

            return deepcopy(install_response)
        elif subcommand == "remove":
            for name in (arg for arg in cmd[2:] if not arg.startswith("-")):
                installed_packages.pop(installed_packages.index(PREFERRED_VERSIONS[name]))
            return {"message": "ok"}
        elif subcommand == "list":
            res = [deepcopy(p) for p in installed_packages]
            for p in res:
                if p["channel"].startswith("http"):
                    p["channel"] = p["channel"].split(f"{REPO_BASE}/")[-1]
            return res
        elif subcommand == "info":
            virtual_packages = [
                ["__unix", "0", "0"],
                ["__linux", "5.10.109", "0"],
                ["__glibc", "2.35", "0"],
                ["__archspec", "1", PLATFORM],
            ]
            info = dict(
                platform=PLATFORM,
                channels=[
                    channel_url(f"{DEFAULT_CHANNEL}/{PLATFORM}"),
                    channel_url(f"{DEFAULT_CHANNEL}/noarch"),
                ],
            )

            if runner != "micromamba":
                info["virtual_pkgs"] = virtual_packages
            else:
                info["virtual packages"] = ["=".join(p) for p in virtual_packages]

            return info
        elif subcommand in ("repoquery", "search"):
            name = next(filter(lambda x: not x.startswith("-") and x != "search", cmd[2:]))
            name = name.split(">")[0].split("<")[0].split("=")[0].split("~")[0]
            packages = [deepcopy(p) for p in conda_info if p["name"] == name]
            if runner != "micromamba":
                return {name: packages}
            return {"result": {"pkgs": packages}}
        else:
            return {"message": "ok"}

    yield mocker.patch("pdm_conda.conda.run_conda", side_effect=_mock)


@pytest.fixture(name="pypi")
def mock_pypi(mocked_responses):
    def _mocker(conda_info, with_dependencies: bool | list[str] | None = None):
        from pdm_conda.models.requirements import parse_conda_version

        _responses = dict()
        if with_dependencies is None:
            with_dependencies = []
        for package in conda_info:
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
            version = parse_conda_version(package["version"])
            url = f"{REPO_BASE}/simple/{name}/"
            _responses[url] = mocked_responses.get(
                url,
                content_type="application/vnd.pypi.simple.v1+json",
                json=dict(
                    files=[
                        {
                            "url": f"{name}#egg={name}-{version}",
                            "requires-python": requires_python,
                            "yanked": None,
                            "dist-info-metadata": False,
                            "hashes": None,
                        },
                    ],
                ),
            )

            if (isinstance(with_dependencies, bool) and with_dependencies) or (
                isinstance(with_dependencies, list) and name in with_dependencies
            ):
                url = f"{REPO_BASE}/pypi/{name}/{version}/json"
                _responses[url] = mocked_responses.get(
                    url,
                    json=dict(
                        info=dict(
                            summary="",
                            requires_python=requires_python,
                            requires=[d.split("|")[0] for d in dependencies],
                        ),
                    ),
                )

            return _responses

    return _mocker


@pytest.fixture(name="installed_packages")
def mock_installed():
    pkgs = {n["name"] for n in PYTHON_REQUIREMENTS}
    return [PREFERRED_VERSIONS[n] for n in pkgs]


@pytest.fixture
def working_set(mocker: MockerFixture) -> dict:
    """
    a mock working set as a fixture

    Returns:
        a mock working set
    """
    from importlib.metadata import Distribution

    from pdm.installers.core import InstallManager
    from pdm.models.candidates import Candidate
    from pdm.models.working_set import WorkingSet

    ws: dict[str, Distribution] = dict()

    def _init_ws(self, *args, **kwargs):
        self._dist_map = ws

    mocker.patch.object(WorkingSet, "__init__", side_effect=_init_ws, autospec=True)

    def install(self, candidate: Candidate) -> None:
        ws[candidate.name] = candidate.prepare(self.environment).metadata

    def uninstall(dist: Distribution) -> None:
        del ws[dist.name]

    mocker.patch.object(InstallManager, "install", side_effect=install, autospec=True)
    mocker.patch.object(InstallManager, "uninstall", side_effect=uninstall)
    return ws


@pytest.fixture
def build_backend(pypi, working_set):
    return pypi([BUILD_BACKEND], with_dependencies=True)


@pytest.fixture
def mocked_responses():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


@pytest.fixture
def mock_conda_mapping(mocker: MockerFixture, mocked_responses, conda_mapping):
    yield mocker.patch("pdm_conda.mapping.download_mapping", return_value=conda_mapping)
    from pdm_conda.mapping import get_pypi_mapping

    get_pypi_mapping.cache_clear()
