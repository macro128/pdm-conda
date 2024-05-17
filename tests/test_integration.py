import json
import subprocess
from pathlib import Path

import pytest

from tests.conftest import PYTHON_VERSION


@pytest.fixture(name="fake_python", autouse=True)
def mock_python(monkeypatch):
    from tests.conftest import CONDA_PREFIX

    monkeypatch.setenv("CONDA_PREFIX", CONDA_PREFIX)


@pytest.fixture
def env_name():
    return "test"


@pytest.fixture
def prepare_env(project, runner):
    project.conda_config.runner = runner
    project.conda_config.solver = "libmamba"
    project.conda_config.channels = ["conda-forge"]
    project.conda_config.as_default_manager = True
    project.conda_config.custom_behavior = True
    project.conda_config.is_initialized = True
    project.global_config["pypi.url"] = "https://pypi.org/simple"
    project.global_config["pypi.json_api"] = False
    if runner in ("conda", "mamba"):
        if runner == "conda":
            pass
        subprocess.run(
            ["micromamba", "install", "-y", runner, "-c", "conda-forge", "-n", "base"],
            check=True,
            capture_output=True,
        )


@pytest.fixture
def clean_envs(pdm, project, env_name, prepare_env):
    while True:
        try:
            pdm(["venv", "remove", env_name, "-y"], obj=project, strict=True, cleanup=True).print()
        except Exception:
            break
    return


@pytest.mark.manual_only
@pytest.mark.usefixtures("clean_envs")
@pytest.mark.parametrize("runner", ["mamba", "micromamba"])
class TestIntegration:
    def assert_lockfile(self, project, pdm=None):
        if pdm is not None:
            res = pdm(["list", "--json"], obj=project, strict=True, cleanup=True)
            res = json.loads(res.stdout)
            installed = {pkg["name"]: pkg for pkg in res}
        for pkg in project.lockfile["package"]:
            assert pkg["groups"], pkg
            if pdm is not None:
                assert pkg["version"] == installed[pkg["name"]]["version"]

    def test_case_01(self, pdm, project, build_env, env_name, runner):
        config = project.conda_config
        config.auto_excludes = True
        config.batched_commands = True
        from pdm_conda.project.core import PyProject

        # python_version = "3.11"
        python_version = PYTHON_VERSION

        print("list environments:")
        pdm(["venv", "list"], obj=project, strict=True, cleanup=True).print()
        print(f"create environment {env_name} with python version {python_version}:")
        pdm(
            ["venv", "create", "-cn", env_name, "-vv", python_version, "-f"],
            obj=project,
            strict=True,
            cleanup=True,
        ).print()
        try:
            # check correct use command
            pdm(["use", "-vv", "--venv", env_name], obj=project, strict=False, cleanup=True).print()
            assert project.python.valid
            python_version = tuple(map(int, python_version.split(".")))  # type: ignore
            assert project.python.version_tuple[: (len(python_version))] == python_version
            for path in project.environment.get_paths().values():
                assert Path(path).exists()

            # print("list packages:")
            # pdm(["list"], obj=project, strict=True, cleanup=True).print()
            print("install conda only package:")
            group = "conda-group"
            pkg_name = "ffmpeg"
            pkg_version = "6.1.1"
            dep = f"{pkg_name}=={pkg_version}"
            pdm(["add", dep, "-G", group, "-vv"], obj=project, strict=True, cleanup=True).print()
            project.pyproject.reload()
            assert pkg_name not in project.conda_config.excludes
            assert project.conda_config.optional_dependencies == {group: [dep]}

            res = pdm(["list", "--json"], obj=project, strict=True, cleanup=True)
            res = json.loads(res.stdout)
            installed = next(filter(lambda r: r["name"] == pkg_name and r["version"] == pkg_version, res), None)
            assert installed is not None
            self.assert_lockfile(project, pdm)

            print("install python-only package:")
            group = "python-group"
            pkg_name = "python-ffmpeg"
            pkg_version = "2.0.12"
            dep = f"{pkg_name}=={pkg_version}"
            pdm(["add", dep, "-G", group], obj=project, strict=True, cleanup=True).print()
            project.pyproject.reload()
            assert project.pyproject.metadata["optional-dependencies"] == {group: [dep]}
            assert group not in project.conda_config.optional_dependencies
            assert pkg_name in project.conda_config.excludes

            res = pdm(["list", "--json"], obj=project, strict=True, cleanup=True)
            res = json.loads(res.stdout)
            installed = next(filter(lambda r: r["name"] == pkg_name and r["version"] == pkg_version, res), None)  # type: ignore
            assert installed is not None
            self.assert_lockfile(project, pdm)

            print("install python-conda package:")
            pkg_name = "pytest"
            pkg_version = "8.0.2"
            group = "dev"
            dep = f"{pkg_name}=={pkg_version}"
            pdm(["add", dep, "-d"], obj=project, strict=True, cleanup=True).print()
            project.pyproject.reload()
            assert project.pyproject.settings["dev-dependencies"] == {group: [dep]}
            assert not project.conda_config.dev_dependencies
            assert pkg_name not in project.conda_config.excludes

            res = pdm(["list", "--json"], obj=project, strict=True, cleanup=True)
            res = json.loads(res.stdout)
            installed = next(filter(lambda r: r["name"] == pkg_name and r["version"] == pkg_version, res), None)  # type: ignore
            assert installed is not None
            expected_pyproject = PyProject(Path(__file__).parent / "data" / "pyproject.toml", ui=project.core.ui)
            expected_pyproject.settings["conda"]["runner"] = runner
            assert project.pyproject._data == expected_pyproject._data
            self.assert_lockfile(project, pdm)

            # print("list environments:")
            # pdm(["venv", "list"], obj=project, strict=True, cleanup=True).print()
        finally:
            print(f"remove environment {env_name}:")
            pdm(["venv", "remove", env_name, "-vv", "-y"], obj=project, strict=True, cleanup=True).print()
        print("list environments:")
        pdm(["venv", "list"], obj=project, strict=True, cleanup=True).print()

    def test_case_02(self, pdm, project, build_env, env_name, runner):
        from pdm_conda.project.core import PyProject

        project.pyproject.set_data(
            PyProject(Path(__file__).parent / "data" / "pyproject.toml", ui=project.core.ui)._data,
        )
        project.pyproject.write()
        project.conda_config.runner = runner
        assert project.conda_config.auto_excludes

        print("lock:")
        pdm(["lock", "-G", ":all", "-vv"], obj=project, strict=True, cleanup=True).print()
        project.pyproject.reload()
        self.assert_lockfile(project)

    def test_case_03(self, pdm, project, build_env, env_name):
        config = project.conda_config
        config.auto_excludes = True
        config.batched_commands = True

        # python_version = "3.11"
        python_version = PYTHON_VERSION

        print("list environments:")
        pdm(["venv", "list"], obj=project, strict=True, cleanup=True).print()
        print(f"create environment {env_name} with python version {python_version}:")
        pdm(
            ["venv", "create", "-cn", env_name, "-vv", python_version, "-f"],
            obj=project,
            strict=True,
            cleanup=True,
        ).print()
        # check correct use command
        pdm(["use", "-vv", "--venv", env_name], obj=project, strict=False, cleanup=True).print()
        assert project.python.valid
        python_version = tuple(map(int, python_version.split(".")))  # type: ignore
        assert project.python.version_tuple[: (len(python_version))] == python_version
        for path in project.environment.get_paths().values():
            assert Path(path).exists()

        print("typer:")
        pdm(["add", "typer", "--no-sync"], obj=project, strict=True, cleanup=True).print()
        project.pyproject.reload()
        self.assert_lockfile(project)

    def test_case_04(self, pdm, project, build_env, env_name, runner):
        from pdm_conda.project.project_file import PyProject

        project.pyproject.set_data(
            PyProject(Path(__file__).parent / "data" / "pyproject_1.toml", ui=project.core.ui)._data,
        )
        project.pyproject.write()
        project.conda_config.runner = runner

        for _ in range(2):
            pdm(["lock", "-G", ":all", "--update-reuse", "-vv"], obj=project, strict=True, cleanup=True).print()
            project.pyproject.reload()
            self.assert_lockfile(project)

    def test_case_05(self, pdm, project, build_env, env_name):
        python_version = "3.11"
        print(f"create environment {env_name} with python version {python_version}:")
        pdm(
            ["venv", "create", "-cn", env_name, "-vv", python_version, "-f"],
            obj=project,
            strict=True,
            cleanup=True,
        ).print()
        print("use")
        res = pdm(["use"], obj=project, strict=True, cleanup=True, input="0\n")
        res.print()
        interpreters = list(project.iter_interpreters())
        assert len(interpreters) == 2
        for i in interpreters:
            assert res.stdout.count(f"({i.executable.parent}") == 1
