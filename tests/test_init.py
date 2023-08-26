from tempfile import TemporaryDirectory

import pytest
from pytest_mock import MockFixture


@pytest.fixture
def change_test_dir(request, monkeypatch):
    with TemporaryDirectory() as td:
        monkeypatch.chdir(td)
        yield


@pytest.mark.usefixtures("change_test_dir")
class TestInit:
    @pytest.mark.parametrize("runner", ["micromamba", "conda", "mamba"])
    @pytest.mark.parametrize("conda_info", [["/opt/conda/bin"], []])
    def test_init_runner(self, pdm, runner, conda, conda_info, mocker: MockFixture):
        mocker.patch("pdm_conda.cli.commands.init.BaseCommand._init_builtin")

        from pdm.core import Core
        from pdm.project.core import Project

        create_project = mocker.spy(Core, "create_project")
        find_interpreters = mocker.spy(Project, "find_interpreters")
        res = pdm(["init", "--runner", runner, "-n"], strict=True)

        project = create_project.spy_return
        assert project.pyproject.read()
        assert project.conda_config.runner == runner
        assert project.pyproject.settings["conda"]["runner"] == runner
        assert "Creating a pyproject.toml for PDM..." in res.stdout
        assert conda.call_count == 1
        (cmd,), kwargs = conda.call_args_list[0]
        assert cmd == [runner, "env", "list", "--json"]
        assert find_interpreters.call_count == 1
