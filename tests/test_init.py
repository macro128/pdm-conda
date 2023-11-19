import pytest
from pytest_mock import MockFixture


@pytest.mark.usefixtures("temp_working_path", "fake_python")
class TestInit:
    @pytest.mark.parametrize("runner", ["micromamba", "conda", "mamba"])
    @pytest.mark.parametrize("channel", ["conda-forge", None])
    @pytest.mark.parametrize("conda_info", [["/opt/conda/bin"], []])
    def test_init_runner(self, pdm, runner, channel, conda, conda_info, mocker: MockFixture):
        mocker.patch("pdm_conda.cli.commands.init.BaseCommand._init_builtin")

        from pdm.core import Core
        from pdm.project.core import Project

        create_project = mocker.spy(Core, "create_project")
        find_interpreters = mocker.spy(Project, "find_interpreters")
        cmd = ["init", "--runner", runner, "-n"]
        if channel:
            cmd.extend(["--channel", channel])
        res = pdm(cmd, strict=True)

        project = create_project.spy_return
        assert project.pyproject.read()
        assert project.conda_config.runner == runner
        assert project.pyproject.settings["conda"]["runner"] == runner
        if channel:
            assert channel in project.conda_config.channels
            assert project.pyproject.settings["conda"]["channels"] == [channel]
        assert "Creating a pyproject.toml for PDM..." in res.stdout
        assert conda.call_count == 1
        (cmd,), kwargs = conda.call_args_list[0]
        assert cmd == [runner, "env", "list", "--json"]
        assert find_interpreters.call_count == 1
