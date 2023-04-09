"""Configuration for the pytest test suite."""
import os
import sys
from copy import deepcopy
from unittest import mock

import pytest
import responses
from pdm.cli.actions import do_init
from pdm.core import Core
from pdm.models.backends import PDMBackend
from pdm.project import Config, Project
from pytest_mock import MockerFixture

from tests.utils import REPO_BASE, generate_package_info

pytest_plugins = "pdm.pytest"

PYTHON_VERSION = sys.version.split(" ")[0]

PYTHON_PACKAGE = generate_package_info("python", PYTHON_VERSION, ["lib 1.0"])
PYTHON_REQUIREMENTS = [
    generate_package_info("openssl", "1.1.1a"),
    generate_package_info("openssl", "1.1.1c"),
    PYTHON_PACKAGE,
]

PREFERRED_VERSIONS = dict()
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
def mock_conda(mocker: MockerFixture, conda_response: dict | list, empty_conda_list: bool):
    if isinstance(conda_response, dict):
        conda_response = [conda_response]
    install_response = {
        "actions": {
            "LINK": conda_response,
        },
    }

    def _mock(cmd, **kwargs):
        runner, subcommand, *_ = cmd
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
            if runner != "micromamba":
                return {
                    "virtual_pkgs": [
                        ["__unix", "0", "0"],
                        ["__linux", "5.10.109", "0"],
                        ["__glibc", "2.35", "0"],
                        ["__archspec", "1", "aarch64"],
                    ],
                }

            return {
                "virtual packages": [
                    "__unix=0=0",
                    "__linux=5.10.109=0",
                    "__glibc=2.35=0",
                    "__archspec=1=aarch64",
                ],
            }
        elif subcommand in ("repoquery", "search"):
            name = next(filter(lambda x: not x.startswith("-") and x != "search", cmd[2:]))
            name = name.split(">")[0].split("<")[0].split("=")[0].split("~")[0]
            packages = [deepcopy(p) for p in conda_response if p["name"] == name]
            if runner != "micromamba":
                return {name: packages}
            return {"result": {"pkgs": packages}}
        else:
            return {"message": "ok"}

    yield mocker.patch("pdm_conda.conda.run_conda", side_effect=_mock)


@pytest.fixture(name="pypi")
def mock_pypi(mocked_responses):
    def _mocker(conda_response, with_dependencies: bool | list[str] | None = None):
        from pdm_conda.models.requirements import parse_conda_version

        _responses = dict()
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


@pytest.fixture
def install_manager(mocker: MockerFixture):
    from pdm.installers.core import install_requirements

    def _install_requirements(*args, **kwargs):
        from pdm.installers.core import InstallManager

        with mock.patch.object(InstallManager, "install"), mock.patch.object(InstallManager, "uninstall"):
            return install_requirements(*args, **kwargs)

    mocker.patch("pdm.installers.core.install_requirements", side_effect=_install_requirements)
    mocker.patch("pdm.installers.manager.install_wheel")
    mocker.patch("pdm.installers.manager.install_wheel_with_cache")
    mocker.patch("pdm.builders.base.BuildBackendHookCaller")
    yield


@pytest.fixture
def build_backend(pypi, install_manager):
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
