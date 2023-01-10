from typing import cast

import pytest

from tests.conftest import CONDA_INFO, PYTHON_REQUIREMENTS


class TestAddRemove:
    conda_runner = "micromamba"

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("empty_conda_list", [False])
    @pytest.mark.parametrize("packages", [["dep"], ["dep", "another-dep"], ["channel::dep", "another-dep"]])
    @pytest.mark.parametrize("channel", [None, "another_channel"])
    @pytest.mark.parametrize("runner", [None, "micromamba"])
    def test_add(self, core, project, mock_conda, conda_response, packages, channel, runner):
        """
        Test `add` command work as expected
        """
        from pdm_conda.models.config import PluginConfig
        from pdm_conda.project import CondaProject

        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": {
                            "runner": runner or self.conda_runner,
                        },
                    },
                },
            },
        )
        command = ["add", "-v", "--no-self", "--no-sync"]
        for p in packages:
            command.extend(["--conda", p])
        if channel:
            command += ["--channel", channel]
        if runner:
            command += ["--runner", runner]
        else:
            runner = self.conda_runner
        core.main(command, obj=project)

        project.pyproject.reload()
        channels = set(p.split("::")[0] for p in packages if "::" in p)
        if channel:
            channels.add(channel)

        conf = PluginConfig.load_config(project)

        assert channels.issubset(conf.channels)
        assert conf.runner == runner

        assert mock_conda.call_count == 3

        project = cast(CondaProject, project)
        dependencies = project.get_conda_pyproject_dependencies("default")
        for p in packages:
            assert any(True for d in dependencies if p in d)
            if channel and "::" not in p:
                assert any(True for d in dependencies if f"{channel}::" in d)

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("empty_conda_list", [False])
    @pytest.mark.parametrize("packages", [["dep"], ["dep", "another-dep"], ["channel::dep"]])
    def test_remove(self, core, project, mock_conda, conda_response, packages):
        self.test_add(core, project, mock_conda, conda_response, packages, None, None)
        mock_conda.reset_mock()
        core.main(["remove", "--no-self"] + packages, obj=project)
        cmd_order = ["list"] + ["remove"] * (len(conda_response) - len(PYTHON_REQUIREMENTS))
        assert mock_conda.call_count == len(cmd_order)
        packages = [p["name"] for p in conda_response]
        for (cmd,), kwargs in mock_conda.call_args_list:
            assert cmd[0] == self.conda_runner
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand == "remove":
                assert any(True for c in cmd if c in packages)
                assert "-f" not in cmd

        assert not cmd_order
