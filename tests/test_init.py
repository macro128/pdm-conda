import itertools

import pytest
from pytest_mock import MockFixture


@pytest.mark.usefixtures("temp_working_path")
class TestInit:
    @pytest.mark.parametrize("runner", ["micromamba", "conda", "mamba"])
    @pytest.mark.parametrize(
        "channels",
        ["conda-forge", "conda-forge,other", ["conda-forge", "other,another-one"], None],
    )
    @pytest.mark.parametrize("conda_info", [["/opt/conda/bin"], []])
    def test_init_runner(self, pdm, runner, channels, conda, conda_info, mocker: MockFixture):
        from pdm.core import Core
        from pdm.project.core import Project

        create_project = mocker.spy(Core, "create_project")
        find_interpreters = mocker.spy(Project, "find_interpreters")
        cmd = ["init", "--runner", runner, "-n"]
        if channels:
            if not isinstance(channels, list):
                channels = [channels]
            for channel in channels:
                cmd.extend(["--channel", channel])
            channels = list(itertools.chain.from_iterable(channel.split(",") for channel in channels))
        res = pdm(cmd, strict=True)

        project = create_project.spy_return
        assert project.pyproject.read()
        assert project.conda_config.runner == runner
        assert project.pyproject.settings["conda"]["runner"] == runner
        if channels:
            assert all(True for c in channels if c in project.conda_config.channels)
            assert project.pyproject.settings["conda"]["channels"] == channels
        assert "Creating a pyproject.toml for PDM..." in res.stdout
        assert find_interpreters.call_count == 1
