import json
from pathlib import Path

import pytest


@pytest.fixture(name="fake_python", autouse=True)
def mock_python(monkeypatch):
    from tests.conftest import CONDA_PREFIX

    monkeypatch.setenv("CONDA_PREFIX", CONDA_PREFIX)


@pytest.mark.manual_only
class TestIntegration:
    def assert_lockfile(self, project, expected_path):
        from pdm_conda.project.core import Lockfile

        expected_lock = Lockfile(expected_path, ui=project.core.ui)
        assert project.lockfile._data == expected_lock._data

    def test_case_01(self, pdm, project, build_env):
        project.global_config["pypi.url"] = "https://pypi.org/simple"
        project.global_config["pypi.json_api"] = False
        config = project.conda_config
        config.runner = "micromamba"
        config.channels = ["conda-forge"]
        config.as_default_manager = True
        config.custom_behavior = True
        config.auto_excludes = True
        config.batched_commands = True
        from pdm_conda.project.core import PyProject

        lockfile_path = Path(__file__).parent / "data" / "pdm.lock"
        name = "test"
        python_version = "3.11"
        # python_version = PYTHON_VERSION

        while True:
            try:
                pdm(["venv", "remove", name, "-y"], obj=project, strict=True, cleanup=True)
            except Exception:
                break

        print("list environments:")
        pdm(["venv", "list"], obj=project, strict=True, cleanup=True).print()
        print(f"create environment {name} with python version {python_version}:")
        pdm(
            ["venv", "create", "-cn", name, "-vv", python_version, "-f"],
            obj=project,
            strict=True,
            cleanup=True,
        ).print()
        try:
            # check correct use command
            pdm(["use", "-vv", "--venv", name], obj=project, strict=False, cleanup=True).print()
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
            pdm(["add", dep, "-G", group], obj=project, strict=True, cleanup=True).print()
            project.pyproject.reload()
            assert pkg_name not in project.conda_config.excludes
            assert project.conda_config.optional_dependencies == {group: [dep]}

            res = pdm(["list", "--json"], obj=project, strict=True, cleanup=True)
            res = json.loads(res.stdout)
            installed = next(filter(lambda r: r["name"] == pkg_name and r["version"] == pkg_version, res), None)
            assert installed is not None
            self.assert_lockfile(project, lockfile_path.with_name("0.lock"))

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
            self.assert_lockfile(project, lockfile_path.with_name("1.lock"))

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
            assert project.pyproject._data == expected_pyproject._data
            self.assert_lockfile(project, lockfile_path.with_name("2.lock"))

            # print("list environments:")
            # pdm(["venv", "list"], obj=project, strict=True, cleanup=True).print()
        finally:
            print(f"remove environment {name}:")
            pdm(["venv", "remove", name, "-vv", "-y"], obj=project, strict=True, cleanup=True).print()
        print("list environments:")
        pdm(["venv", "list"], obj=project, strict=True, cleanup=True).print()

    def test_case_02(self, pdm, project, build_env):
        from pdm_conda.project.core import PyProject

        lockfile_path = Path(__file__).parent / "data" / "pdm.lock"
        project.pyproject.set_data(PyProject(Path(__file__).parent / "data" / "pyproject.toml", ui=project.core.ui))
        project.pyproject.write()
        name = "test"
        python_version = "3.11"

        while True:
            try:
                pdm(["venv", "remove", name, "-y"], obj=project, strict=True, cleanup=True)
            except Exception:
                break

        print("list environments:")
        pdm(["venv", "list"], obj=project, strict=True, cleanup=True).print()
        print(f"create environment {name} with python version {python_version}:")
        pdm(
            ["venv", "create", "-cn", name, "-vv", python_version, "-f"],
            obj=project,
            strict=True,
            cleanup=True,
        ).print()
        try:
            # check correct use command
            pdm(["use", "-vv", "--venv", name], obj=project, strict=False, cleanup=True).print()
            assert project.python.valid
            python_version = tuple(map(int, python_version.split(".")))  # type: ignore
            assert project.python.version_tuple[: (len(python_version))] == python_version
            for path in project.environment.get_paths().values():
                assert Path(path).exists()

            print("lock:")
            pdm(["lock", "-G", ":all"], obj=project, strict=True, cleanup=True).print()
            project.pyproject.reload()
            self.assert_lockfile(project, lockfile_path.with_name("2.lock"))

            # print("list environments:")
            # pdm(["venv", "list"], obj=project, strict=True, cleanup=True).print()
        finally:
            print(f"remove environment {name}:")
            pdm(["venv", "remove", name, "-vv", "-y"], obj=project, strict=True, cleanup=True).print()
        print("list environments:")
        pdm(["venv", "list"], obj=project, strict=True, cleanup=True).print()
