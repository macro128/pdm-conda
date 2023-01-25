import pytest

from tests.conftest import CONDA_INFO, CONDA_MAPPING, PYTHON_REQUIREMENTS
from tests.utils import format_url


class TestInstall:
    conda_runner = "micromamba"

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("empty_conda_list", [True])
    @pytest.mark.parametrize("dry_run", [True, False])
    @pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
    def test_install(
        self,
        core,
        project,
        mock_conda,
        conda_response,
        dry_run,
        mock_conda_mapping,
    ):
        """
        Test `install` command work as expected
        """
        dependency = conda_response[-1]["name"]
        conf = project.conda_config
        conf.runner = self.conda_runner
        conf.dependencies = [dependency]
        command = ["install", "-v", "--no-self"]
        if dry_run:
            command.append("--dry-run")
        core.main(command, obj=project)

        conda_calls = len({r["name"] for r in conda_response if r not in PYTHON_REQUIREMENTS})
        cmd_order = (
            ["info", "search", "list"]
            + ["search"] * (conda_calls + len(PYTHON_REQUIREMENTS) - 1)
            + ["list"]
            + ["install"] * (0 if dry_run else conda_calls)
        )
        assert mock_conda.call_count == len(cmd_order)

        urls = []
        i = 0
        while i < len(conda_response):
            if (p := conda_response[i]) not in PYTHON_REQUIREMENTS:
                version = p["version"]
                name = p["name"]
                i += 1
                while i < len(conda_response) and (other_p := conda_response[i])["name"] == name:
                    if version == other_p["version"]:
                        p = other_p
                    i += 1
                urls.append(format_url(p))
            else:
                i += 1
        for (cmd,), kwargs in mock_conda.call_args_list:
            assert cmd[0] == self.conda_runner
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand == "install":
                deps = kwargs["dependencies"]
                assert len(deps) == 1
                urls.remove(deps[0])

        if not dry_run:
            assert not urls
        assert not cmd_order
