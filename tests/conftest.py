"""Configuration for the pytest test suite."""

import os
import sys
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from pdm.core import Core
from pdm.models.backends import PDMBackend
from pdm.project import Config
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from tests.utils import DEFAULT_CHANNEL, PLATFORM, REPO_BASE, channel_url, generate_package_info

pytest_plugins = "pdm.pytest"

PYTHON_VERSION = sys.version.split(" ")[0]

PYTHON_PACKAGE = generate_package_info("python", PYTHON_VERSION, ["lib 1.0", "__unix =0"])
PYTHON_REQUIREMENTS = [
    generate_package_info("openssl", "1.1.1a"),
    generate_package_info("openssl", "1.1.1c"),
    PYTHON_PACKAGE,
]

PREFERRED_VERSIONS = {"python": PYTHON_PACKAGE}
_python_dep = f"python >={PYTHON_VERSION}"
_packages = [
    generate_package_info("python-only-dep", "1.0", python_only=True),
    generate_package_info("pip", "1.0"),
    generate_package_info("openssl", "1.1.1b"),
    generate_package_info("lib2", "1.0.0g"),
    generate_package_info("lib", "1.0", ["lib2 ==1.0.0g", "openssl >=1.1.1a,<1.1.1c"]),
]
for _p in _packages:
    PREFERRED_VERSIONS[_p["name"]] = _p
    PYTHON_REQUIREMENTS.append(_p)
PYTHON_REQUIREMENTS.extend(PREFERRED_VERSIONS.values())

CONDA_REQUIREMENTS = [
    generate_package_info("conda", "1.0"),
    generate_package_info("mamba", "1.0", depends=["conda"]),
]
for _p in CONDA_REQUIREMENTS:
    PREFERRED_VERSIONS[_p["name"]] = _p

_CONDA_INFO = [
    *(pkg for pkg in PYTHON_REQUIREMENTS if not pkg["python_only"]),
    generate_package_info("another-dep", "1!0.1gg", depends=["lib ==1.0"]),
    generate_package_info("another-dep", "1!0.1gg", timestamp=3),
    generate_package_info(
        "another-dep",
        "1!0.1gg",
        build_number=1,
        timestamp=4,
        channel=f"{DEFAULT_CHANNEL}/noarch",
    ),
    generate_package_info("another-dep", "1!0.1gg", timestamp=1),
]

_packages = [
    generate_package_info("another-dep", "1!0.1gg", timestamp=2, build_number=1),
    generate_package_info("another-python-dep", "0.1b0", timestamp=2, build_number=1),
    generate_package_info(
        "dep",
        "1.0.0",
        depends=[_python_dep, "another-dep ==1!0.1gg|==1!0.0g", "another-python-dep"],
        timestamp=2,
        build_number=1,
    ),
]
for _p in _packages:
    PREFERRED_VERSIONS[_p["name"]] = _p
    _CONDA_INFO.append(_p)

CONDA_MAPPING = {f"{p['name']}-pip": p["name"] for p in _CONDA_INFO}
CONDA_INFO = [*_CONDA_INFO]
BUILD_BACKEND = generate_package_info("pdm-backend", "2.0")
CONDA_PREFIX = os.getenv("CONDA_PREFIX")


@pytest.fixture(scope="session", autouse=True)
def tmp_cwd():
    with TemporaryDirectory() as tmp:
        _cwd = Path.cwd()
        os.chdir(tmp)
        yield Path(tmp)
        os.chdir(_cwd)


@pytest.fixture(autouse=True)
def test_name():
    return os.getenv("PYTEST_CURRENT_TEST", "").split(":")[-1]


@pytest.fixture
def test_id(test_name):
    return test_name.split("[")[-1].split("]")[0]


@pytest.fixture(scope="session")
def build_env():
    with TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture(name="core")
def core_with_plugin(core, monkeypatch) -> Core:
    from pdm_conda import main

    Config._config_map["python.use_venv"].default = True
    for conf in [
        "INSTALLATION_METHOD",
        "RUNNER",
        "SOLVER",
        "AS_DEFAULT_MANAGER",
        "BATCHED_COMMANDS",
        "CUSTOM_BEHAVIOR",
    ]:
        monkeypatch.delenv(f"PDM_CONDA_{conf}", raising=False)
    main(core)
    return core


@pytest.fixture
def project(core, project_no_init, monkeypatch):
    _project = project_no_init
    _project.global_config["check_update"] = False
    _project.global_config["pypi.json_api"] = True
    _project.global_config["pypi.url"] = f"{REPO_BASE}/simple"
    from pdm.cli.utils import merge_dictionary

    data = {
        "project": {
            "name": "test-project",
            "version": "0.0.0",
            "description": "",
            "authors": [],
            "license": {"text": "MIT"},
            "dependencies": [],
            "requires-python": f">={PYTHON_VERSION}",
        },
        "build-system": PDMBackend.build_system(),
    }

    merge_dictionary(_project.pyproject._data, data)
    _project.pyproject.write()
    # Clean the cached property
    _project._environment = None
    monkeypatch.setenv("CONDA_PREFIX", CONDA_PREFIX)
    return _project


@pytest.fixture(name="pdm")
def pdm_run(core, pdm):
    return pdm


@pytest.fixture
def num_missing_info_on_create():
    return 0


@pytest.fixture
def conda_info():
    return CONDA_INFO


@pytest.fixture
def conda_mapping():
    return dict(CONDA_MAPPING)


@pytest.fixture(name="conda")
def mock_conda(
    httpx_mock,
    mocker: MockerFixture,
    conda_info: dict | list,
    num_missing_info_on_create: int,
    installed_packages,
):
    if isinstance(conda_info, dict):
        conda_info = [conda_info]

    def _mock(cmd, **kwargs):
        runner, subcommand, *_ = cmd
        if subcommand == "install":
            install_response = []
            packages = list(kwargs["lockfile"])
            assert packages.pop(0) == "@EXPLICIT"
            for url in (p for p in packages if p.startswith("https://")):
                install_response += [p for p in PREFERRED_VERSIONS.values() if url.startswith(p["url"])]
            installed_packages.extend(install_response)

            return {"actions": {"LINK": deepcopy(install_response)}}
        if subcommand == "remove":
            for name in (arg for arg in cmd[5:] if not arg.startswith("-")):
                installed_packages.pop(installed_packages.index(PREFERRED_VERSIONS[name]))
            return {"message": "ok"}
        if subcommand == "env" and cmd[2] == "list":
            return {"envs": conda_info}
        if subcommand == "list":
            res = [deepcopy(p) for p in installed_packages]
            if runner in ("conda", "mamba"):
                res.append(deepcopy(PREFERRED_VERSIONS["conda"]))
                if runner == "mamba":
                    res.append(deepcopy(PREFERRED_VERSIONS["mamba"]))
            for p in res:
                if p["channel"].startswith("http"):
                    p["channel"] = p["channel"].split(f"{REPO_BASE}/")[-1]
            return res
        if subcommand == "info":
            virtual_packages = [
                ["__unix", "0", "0"],
                ["__linux", "5.10.109", "0"],
                ["__glibc", "2.35", "0"],
                ["__archspec", "1", PLATFORM],
            ]
            info: dict[str, Any] = {
                "platform": PLATFORM,
                "channels": [
                    channel_url(f"{DEFAULT_CHANNEL}/{PLATFORM}"),
                    channel_url(f"{DEFAULT_CHANNEL}/noarch"),
                ],
            }
            base_env = "/opt/conda/base"
            if runner != "micromamba":
                info["virtual_pkgs"] = virtual_packages
                info["base environment"] = base_env
            else:
                info["virtual packages"] = ["=".join(p) for p in virtual_packages]
                info["root_prefix"] = base_env

            return info
        if subcommand in ("repoquery", "search"):
            name = next(filter(lambda x: not x.startswith("-") and x != "search", cmd[2:]))
            name = name.split(">")[0].split("<")[0].split("=")[0].split("~")[0]
            packages = [deepcopy(p) for p in conda_info + CONDA_REQUIREMENTS if p["name"] == name]
            if runner != "micromamba":
                return {name: packages}
            return {"result": {"pkgs": packages}}
        if subcommand == "create":

            def _fetch_package(req, packages, fetch_info):
                name = req.split(" ")[0].split(":")[-1].split("=")[0].split("<")[0].split(">")[0].strip("\"'")
                if name not in packages and not name.startswith("__"):
                    packages.add(name)
                    pkg = PREFERRED_VERSIONS[name]
                    if pkg["python_only"]:
                        from pdm_conda.conda import CondaResolutionError

                        raise CondaResolutionError(data={"message": f"nothing provides requested {req}"})
                    fetch_info.append(deepcopy(pkg))
                    for d in pkg["depends"]:
                        _fetch_package(d, packages, fetch_info)

            _packages: set[dict] = set()
            fetch_info: list[dict] = []
            i = 2
            while i < len(cmd):
                req = cmd[i]
                i += 1
                if req == "-c":
                    break
                if req.startswith("-"):
                    if req in ("--prefix", "--solver"):
                        i += 1
                    continue
                _fetch_package(req, _packages, fetch_info)

            link_info = deepcopy(fetch_info)
            if runner != "micromamba":
                for p in link_info:
                    p.pop("depends")
                    p.pop("constrains")
                fetch_info = fetch_info[num_missing_info_on_create:]
            return {"actions": {"FETCH": fetch_info, "LINK": link_info}}
        return {"message": "ok"}

    mocker.patch("pdm_conda.conda.which")
    return mocker.patch("pdm_conda.conda.run_conda", side_effect=_mock)


@pytest.fixture(name="pypi")
def mock_pypi(httpx_mock: HTTPXMock):
    def _mocker(conda_info, with_dependencies: bool | list[str] | None = None):
        from pdm_conda.mapping import conda_to_pypi
        from pdm_conda.models.requirements import parse_conda_version

        if with_dependencies is None:
            with_dependencies = []
        for package in conda_info:
            dependencies = list(package["depends"])
            requires_python = ""
            to_delete = []
            name = conda_to_pypi(package["name"])
            version = parse_conda_version(package["version"])
            if package.get("extras", []):
                dependencies.append(f"{name}=={version}")

            for d in dependencies:
                if d.startswith("__"):
                    to_delete.append(d)
                elif d.startswith("python "):
                    to_delete.append(d)
                    if not requires_python:
                        requires_python = d.split(" ")[-1]
            for d in to_delete:
                dependencies.remove(d)
            url = f"{REPO_BASE}/simple/{name}/"
            httpx_mock.add_response(
                url=url,
                method="GET",
                headers={"Content-Type": "application/vnd.pypi.simple.v1+json"},
                json={
                    "files": [
                        {
                            "url": f"{name}#egg={name}-{version}",
                            "requires-python": requires_python,
                            "yanked": None,
                            "dist-info-metadata": False,
                            "hashes": None,
                        },
                    ],
                },
            )

            if (isinstance(with_dependencies, bool) and with_dependencies) or (
                isinstance(with_dependencies, list) and name in with_dependencies
            ):
                url = f"{REPO_BASE}/pypi/{name}/{version}/json"
                httpx_mock.add_response(
                    url=url,
                    method="GET",
                    json={
                        "info": {
                            "summary": "",
                            "requires_python": requires_python,
                            "requires": [d.split("|")[0] for d in dependencies],
                        },
                    },
                )

    return _mocker


@pytest.fixture(name="installed_packages")
def mock_installed():
    pkgs = {n["name"] for n in PYTHON_REQUIREMENTS if not n["python_only"]}
    return [PREFERRED_VERSIONS[n] for n in pkgs]


@pytest.fixture
def working_set(mocker: MockerFixture) -> dict:
    """A mock working set as a fixture.

    Returns:
        a mock working set
    """
    from importlib.metadata import Distribution

    from pdm.installers.manager import InstallManager
    from pdm.models.candidates import Candidate
    from pdm.models.working_set import WorkingSet

    ws: dict[str, Distribution] = {}

    def _init_ws(self, *args, **kwargs):
        self._dist_map = ws

    mocker.patch.object(WorkingSet, "__init__", side_effect=_init_ws, autospec=True)

    def install(self, candidate: Candidate) -> None:
        ws[candidate.name] = candidate.prepare(self.environment).metadata

    def uninstall(dist: Distribution) -> None:
        ws.pop(dist.name)

    mocker.patch.object(InstallManager, "install", side_effect=install, autospec=True)
    mocker.patch.object(InstallManager, "uninstall", side_effect=uninstall)
    return ws


@pytest.fixture
def build_backend(pypi, working_set):
    pypi([BUILD_BACKEND], with_dependencies=True)


@pytest.fixture
def mock_conda_mapping(mocker: MockerFixture, httpx_mock, conda_mapping):
    mocker.patch("pdm_conda.mapping.get_mapping_fixes", return_value={})
    return mocker.patch("pdm_conda.mapping.get_pypi_mapping", return_value=conda_mapping)


@pytest.fixture
def interpreter_path():
    return None


@pytest.fixture
def venv_path():
    return None


@pytest.fixture(name="fake_python", autouse=True)
def mock_python(mocker: MockerFixture, interpreter_path, venv_path, monkeypatch):
    from findpython import PythonVersion
    from packaging.version import Version
    from pdm.environments import BaseEnvironment

    monkeypatch.setenv("CONDA_PREFIX", venv_path or CONDA_PREFIX)
    mocker.patch.object(PythonVersion, "_get_version", return_value=Version(PYTHON_VERSION))
    mocker.patch.object(PythonVersion, "_get_architecture", return_value="aarch64")
    mocker.patch.object(
        PythonVersion,
        "_get_interpreter",
        return_value=interpreter_path or f"{CONDA_PREFIX}/bin/python",
    )
    mocker.patch.object(BaseEnvironment, "_patch_target_python")


@pytest.fixture
def temp_working_path(request, monkeypatch):
    with TemporaryDirectory() as td:
        monkeypatch.chdir(td)
        yield td
