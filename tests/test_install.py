import pytest

from tests.conftest import CONDA_INFO, PYTHON_REQUIREMENTS
from tests.utils import format_url


class TestInstall:
    conda_runner = "micromamba"

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("empty_conda_list", [True])
    @pytest.mark.parametrize("dry_run", [True, False])
    def test_install(self, core, project, mock_conda, conda_response, dry_run):
        """
        Test `install` command work as expected
        """
        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": {
                            "runner": self.conda_runner,
                            "dependencies": [conda_response[-1]["name"]],
                        },
                    },
                },
            },
        )
        command = ["install", "-v", "--no-self"]
        if dry_run:
            command.append("--dry-run")
        core.main(command, obj=project)

        conda_calls = len(conda_response) - len(PYTHON_REQUIREMENTS)
        cmd_order = ["info"] + ["search"] * conda_calls + ["list"] + ["install"] * (0 if dry_run else conda_calls)
        assert mock_conda.call_count == len(cmd_order)

        urls = [format_url(p) for p in conda_response if p not in PYTHON_REQUIREMENTS]
        for (cmd,), kwargs in mock_conda.call_args_list:
            assert cmd[0] == self.conda_runner
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand == "install":
                # if not install_dep:
                #     assert set(kwargs["dependencies"]) == requirements
                #     if not dry_run:
                #         install_dep = True
                # else:
                deps = kwargs["dependencies"]
                assert len(deps) == 1
                urls.remove(deps[0])

        if not dry_run:
            assert not urls
        assert not cmd_order
