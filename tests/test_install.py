import re

import pytest

from tests.conftest import CONDA_INFO, CONDA_MAPPING, PYTHON_REQUIREMENTS
from tests.utils import format_url


class TestInstall:
    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("runner", ["conda", "micromamba"])
    @pytest.mark.parametrize("empty_conda_list", [True])
    @pytest.mark.parametrize("dry_run", [True, False])
    @pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
    def test_install(
        self,
        pdm,
        project,
        conda,
        conda_response,
        runner,
        dry_run,
        mock_conda_mapping,
    ):
        """
        Test `install` command work as expected
        """
        conda_response = [r for r in conda_response if r not in PYTHON_REQUIREMENTS]
        conf = project.conda_config
        conf.runner = runner
        conf.dependencies = [conda_response[-1]["name"]]
        command = ["install", "-v", "--no-self"]
        if dry_run:
            command.append("--dry-run")
        result = pdm(command, obj=project)
        assert result.exception is None

        packages_to_install = {r["name"]: None for r in conda_response}
        num_installs = len(packages_to_install)
        if dry_run:
            out = "Packages to add:\n"
            for p in packages_to_install:
                out += f"\\s+- {p} [^\n]+\n"
            assert re.search(out, result.stdout)
        else:
            assert f"{num_installs} to add" in result.stdout

        cmd_order = (
            ["list", "info", "search"]
            + ["search"] * num_installs
            + ["list"]
            + ["install"] * (0 if dry_run else num_installs)
        )
        assert conda.call_count == len(cmd_order)

        urls = dict()
        for p in conda_response:
            urls[p["name"]] = format_url(p)
        urls = list(urls.values())
        for (cmd,), kwargs in conda.call_args_list:
            assert cmd[0] == runner
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand == "install":
                deps = kwargs["dependencies"]
                assert len(deps) == 1
                urls.remove(deps[0])

        if not dry_run:
            assert not urls
        assert not cmd_order
