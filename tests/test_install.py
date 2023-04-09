import re

import pytest

from tests.conftest import BUILD_BACKEND, CONDA_INFO, CONDA_MAPPING, PYTHON_REQUIREMENTS
from tests.utils import format_url


class TestInstall:
    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("runner", ["conda", "micromamba"])
    @pytest.mark.parametrize("empty_conda_list", [True])
    @pytest.mark.parametrize("dry_run", [True, False])
    @pytest.mark.parametrize("conda_batched", [True, False])
    @pytest.mark.parametrize("install_self", [True, False])
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
        conda_batched,
        install_self,
        build_backend,
    ):
        """
        Test `install` command work as expected
        """
        conda_response = [r for r in conda_response if r not in PYTHON_REQUIREMENTS]
        conf = project.conda_config
        conf.runner = runner
        conf.dependencies = [conda_response[-1]["name"]]
        conf.batched = conda_batched
        command = ["install", "-vv"]
        if not install_self:
            command.append("--no-self")

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
            if install_self:
                assert f"Install {project.name} {project.pyproject.metadata.get('version')} successful" in result.output
                assert f"Installing {BUILD_BACKEND['name']} {BUILD_BACKEND['version']}" in result.outputs
            assert f"{num_installs} to add" in result.stdout

        search_cmd = "search" if runner == "conda" else "repoquery"
        cmd_order = (
            ["list", "info", search_cmd]
            + [search_cmd] * num_installs
            + ["list"]
            + ["install"] * (0 if dry_run else (1 if conda_batched else num_installs))
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
                if conda_batched:
                    assert len(deps) == num_installs
                else:
                    assert len(deps) == 1
                for u in deps:
                    urls.remove(u)

        if not dry_run:
            assert not urls
        assert not cmd_order
