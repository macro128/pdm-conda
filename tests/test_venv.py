from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from conftest import CONDA_PREFIX
from pdm.project import Config


@pytest.fixture(name="conda_envs_path")
def patch_listed_envs(project, monkeypatch):
    with TemporaryDirectory() as td:
        venvs_path = Path(td) / "envs"
        yield venvs_path


@pytest.fixture
def venv_path(project, conda_name, conda_envs_path):
    from pdm.cli.commands.venv.utils import get_venv_prefix

    return conda_envs_path / (conda_name if conda_name else get_venv_prefix(project))


@pytest.fixture
def active():
    return True


@pytest.fixture
def initialized():
    return True


@pytest.fixture
def interpreter_path(venv_path, active, initialized):
    path = venv_path / "bin/python"
    if initialized:
        path.mkdir(exist_ok=True, parents=True)
        (venv_path / "conda-meta").mkdir(exist_ok=True)
    return path if active else None


@pytest.fixture
def conda_info(venv_path):
    return [CONDA_PREFIX, str(venv_path)]


@pytest.mark.usefixtures("venv_path")
class TestVenv:
    @pytest.mark.parametrize("runner", ["micromamba", "conda", "mamba"])
    @pytest.mark.parametrize("with_pip", [True, False])
    @pytest.mark.parametrize("conda_name", ["test", None])
    @pytest.mark.parametrize("venv_location", [None, "/tmp"])
    def test_venv_create(
        self,
        pdm,
        project,
        runner,
        conda_name,
        with_pip,
        venv_location,
        monkeypatch,
        conda,
        conda_envs_path,
    ):
        """Test `venv create` command work as expected."""
        project.global_config["venv.location"] = Config.get_defaults()["venv.location"]
        cmd = ["venv", "create", "-w", runner, "--force"]
        if conda_name:
            cmd.extend(["-n", f"{conda_name}", "-cn", conda_name])
        if with_pip:
            cmd.append("--with-pip")
        if venv_location:
            project.global_config["venv.location"] = venv_location
        with project.conda_config.with_conda_venv_location() as (_venv_location, overridden):
            assert overridden != bool(venv_location)
            assert _venv_location == Path(conda_envs_path if overridden else venv_location)

        if project.config:
            del project.config

        pdm(cmd, obj=project, strict=True)

        cmd_order = ["info", "create"]
        if conda_name and not venv_location:
            cmd_order = ["env"] + cmd_order
        venv_name = conda_name if conda_name else f"{project.root.name}-"
        assert conda.call_count == len(cmd_order)
        for (cmd,), _ in conda.call_args_list:
            assert (conda_venv_command := cmd[1]) in cmd_order
            if conda_venv_command == "create":
                assert (idx := cmd.index("--prefix")) != -1
                env_prefix = Path(cmd[idx + 1])
                assert venv_name in env_prefix.name
                if with_pip:
                    assert "pip" in cmd
                if venv_location:
                    assert env_prefix.parent == Path(venv_location)
                else:
                    assert env_prefix.parent == conda_envs_path
                    assert conda_envs_path != project.config["venv.location"]
            elif conda_venv_command != "info":
                assert (prefix_index := cmd.index("--prefix")) != -1
                assert venv_name in cmd[prefix_index + 1]

        assert project.conda_config.runner == runner

    @pytest.mark.parametrize("runner", ["micromamba", "conda", "mamba"])
    @pytest.mark.parametrize(
        "initialized,conda_name,active",
        [[True, "test", True]],
    )
    def test_venv_list(
        self,
        pdm,
        project,
        runner,
        initialized,
        conda_name,
        monkeypatch,
        mocker,
        conda_envs_path,
        active,
        interpreter_path,
        venv_path,
        conda,
    ):
        """Test `venv list` command work as expected."""
        project.global_config["venv.location"] = Config.get_defaults()["venv.location"]
        # Ignore saved python and search for activated venv
        monkeypatch.setenv("PDM_IGNORE_SAVED_PYTHON", "1" if active else "0")
        if active and conda_name:
            mocker.patch.object(project, "root", new=venv_path)
        if initialized:
            with project.conda_config.write_project_config():
                project.conda_config.runner = runner

        result = pdm(["venv", "list"], obj=project, strict=True)
        if initialized:
            if conda_name:
                if active:
                    assert conda_name in result.output
                else:
                    assert conda_name not in result.output
            else:
                assert f"{project.root.name}-" in result.output

        assert "Virtualenv is created successfully" not in result.output
        conda_calls = ["env list", "info"]
        assert conda.call_count == len(conda_calls)
        for ((cmd,), _), expected_cmd in zip(conda.call_args_list, conda_calls, strict=False):
            assert " ".join(cmd).startswith(f"{runner} {expected_cmd}")
