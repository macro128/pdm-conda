import re

import pytest

from tests.conftest import CONDA_INFO, CONDA_MAPPING, PYTHON_REQUIREMENTS
from tests.utils import format_url


@pytest.mark.usefixtures("working_set")
class TestInstall:
    @pytest.mark.parametrize("conda_info", CONDA_INFO)
    @pytest.mark.parametrize("runner", ["conda", "micromamba"])
    @pytest.mark.parametrize("dry_run", [True, False])
    @pytest.mark.parametrize("conda_batched", [True, False, None])
    @pytest.mark.parametrize("install_self", [True, False])
    @pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
    def test_install(
        self,
        pdm,
        project,
        conda,
        conda_info,
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
        conda_info = [r for r in conda_info if r not in PYTHON_REQUIREMENTS]
        conf = project.conda_config
        conf.runner = runner
        conf.dependencies = [conda_info[-1]["name"]]
        if conda_batched is None:
            conda_batched = False
        else:
            conf.batched_commands = conda_batched
        command = ["install", "-vv"]
        if not install_self:
            command.append("--no-self")

        if dry_run:
            command.append("--dry-run")
        result = pdm(command, obj=project, strict=True)

        packages_to_install = {r["name"]: None for r in conda_info}
        num_installs = len(packages_to_install)
        if dry_run:
            out = "Packages to add:\n"
            for p in packages_to_install:
                out += f"\\s+- {p} [^\n]+\n"
            assert re.search(out, result.stdout)
        else:
            if install_self:
                assert f"Install {project.name} {project.pyproject.metadata.get('version')} successful" in result.output
            assert f"{num_installs} to add" in result.stdout

        cmd_order = ["create", "list"] + ["install"] * (0 if dry_run else (1 if conda_batched else num_installs))
        assert conda.call_count == len(cmd_order)

        urls = dict()
        for p in conda_info:
            urls[p["name"]] = format_url(p)
        urls = list(urls.values())
        for (cmd,), kwargs in conda.call_args_list:
            assert cmd[0] == runner
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand == "install":
                deps = [c for c in cmd if c.startswith("https://")]
                if conda_batched:
                    assert len(deps) == num_installs
                else:
                    assert len(deps) == 1
                for u in deps:
                    urls.remove(u)

        if not dry_run:
            assert not urls
        assert not cmd_order
