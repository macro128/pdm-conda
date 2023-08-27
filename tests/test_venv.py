from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pdm.project import Config


@pytest.mark.usefixtures("debug_fix")
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
    ):
        """
        Test `venv create` command work as expected
        """
        with TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("VIRTUAL_ENV", tmpdir)
            project.global_config["venv.location"] = Config.get_defaults()["venv.location"]
            cmd = ["venv", "create", "-w", runner]
            if conda_name:
                cmd.extend(["-n", f"{conda_name}", "-cn", conda_name])
            if with_pip:
                cmd.append("--with-pip")
            conda_venv_path = Path(tmpdir) / "envs/"
            if venv_location:
                project.global_config["venv.location"] = venv_location
            else:
                conda_venv_path.mkdir(exist_ok=True)
                with project.conda_config.with_conda_venv_location() as (_venv_location, _):
                    assert _venv_location == conda_venv_path

            if project.config:
                del project.config

            pdm(cmd, obj=project, strict=True)

        assert conda.call_count == 1
        for (cmd,), kwargs in conda.call_args_list:
            assert cmd[1] == "create"
            assert (env_prefix := cmd.index("--prefix")) != -1
            env_prefix = Path(cmd[env_prefix + 1])
            if conda_name:
                assert env_prefix.name == conda_name
            else:
                assert f"{project.root.name}-" in env_prefix.name
            if with_pip:
                assert "pip" in cmd
            if venv_location:
                assert env_prefix.parent == Path(venv_location)
            else:
                assert env_prefix.parent == conda_venv_path
                assert conda_venv_path != project.config["venv.location"]

        assert project.conda_config.runner == runner

    # @pytest.mark.parametrize("runner", ["micromamba", "conda", "mamba"])
    # def test_venv_list(
    #     self,
    #     pdm,
    #     project,
    #     runner,
    #     monkeypatch,
    #     conda
    # ):
    #     """
    #     Test `venv list` command work as expected
    #     """
    #     project.conda_config.runner = runner
    #     pdm(["venv", "list"], obj=project, strict=True)
