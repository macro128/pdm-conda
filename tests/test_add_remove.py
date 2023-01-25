from typing import cast

import pytest

from tests.conftest import CONDA_INFO, CONDA_MAPPING, PYTHON_REQUIREMENTS


class TestAddRemove:
    conda_runner = "micromamba"

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("empty_conda_list", [False])
    @pytest.mark.parametrize("packages", [["dep"], ["dep", "another-dep"], ["channel::dep", "another-dep"]])
    @pytest.mark.parametrize("channel", [None, "another_channel"])
    @pytest.mark.parametrize("runner", [None, "micromamba"])
    @pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
    def test_add(self, core, project, mock_conda, conda_response, packages, channel, runner, mock_conda_mapping):
        """
        Test `add` command work as expected
        """
        from pdm_conda.project import CondaProject

        project = cast(CondaProject, project)
        conf = project.conda_config
        conf.runner = runner or self.conda_runner
        conf.channels = []
        command = ["add", "-v", "--no-self", "--no-sync"]
        for package in packages:
            command.extend(["--conda", package])
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

        assert channels.issubset(conf.channels)
        assert conf.runner == runner

        num_search = 2 + len(PYTHON_REQUIREMENTS)  # add conda info, list and python packages
        packages_names = {p.split("::")[-1] for p in packages}
        to_search = set()
        for c in conda_response:
            if (name := c["name"]) in packages_names and name not in to_search:
                num_search += 1 + len([d for d in c["depends"] if not d.startswith("python ")])
                to_search.add(name)
        assert mock_conda.call_count == num_search

        dependencies = project.get_conda_pyproject_dependencies("default")
        for package in packages:
            _package = package.split("::")[-1]
            assert any(True for d in dependencies if _package in d)

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("empty_conda_list", [False])
    @pytest.mark.parametrize("packages", [["dep"], ["dep", "another-dep"], ["channel::dep"]])
    @pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
    def test_remove(self, core, project, mock_conda, conda_response, packages, mock_conda_mapping):
        self.test_add(core, project, mock_conda, conda_response, packages, None, None, mock_conda_mapping)
        mock_conda.reset_mock()
        core.main(["remove", "--no-self"] + packages, obj=project)
        conda_calls = len({p["name"] for p in conda_response}) - len(PYTHON_REQUIREMENTS)
        cmd_order = []
        if conda_calls:
            cmd_order = ["list"] + ["remove"] * conda_calls
        assert mock_conda.call_count == len(cmd_order)
        packages = [p["name"] for p in conda_response]
        python_packages = [f"{p['name']}=={p['version']}" for p in PYTHON_REQUIREMENTS]
        for (cmd,), kwargs in mock_conda.call_args_list:
            assert cmd[0] == self.conda_runner
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand in ("remove", "search"):
                name = next(filter(lambda x: not x.startswith("-"), cmd[2:]))
                if cmd_subcommand == "remove":
                    assert name in packages
                    assert "-f" not in cmd
                elif cmd_subcommand == "search":
                    assert name in python_packages

        assert not cmd_order
