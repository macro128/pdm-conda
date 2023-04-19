from typing import cast

import pytest

from tests.conftest import (
    CONDA_INFO,
    CONDA_MAPPING,
    PREFERRED_VERSIONS,
    PYTHON_REQUIREMENTS,
)


@pytest.mark.parametrize("conda_info", CONDA_INFO)
@pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
@pytest.mark.parametrize("runner", [None, "micromamba", "conda"])
@pytest.mark.usefixtures("working_set")
@pytest.mark.parametrize("group", ["default", "other"])
class TestAddRemove:
    default_runner = "micromamba"

    @pytest.mark.parametrize(
        "packages",
        [["'dep'"], ["'another-dep==1!0.1gg'"], ['"dep"', "another-dep"], ["'channel::dep'", "another-dep"]],
    )
    @pytest.mark.parametrize("channel", [None, "another_channel"])
    def test_add(
        self,
        pdm,
        project,
        conda,
        packages,
        channel,
        runner,
        mock_conda_mapping,
        installed_packages,
        group,
    ):
        """
        Test `add` command work as expected
        """
        from pdm_conda.project import CondaProject

        project = cast(CondaProject, project)
        conf = project.conda_config
        conf.runner = runner or self.default_runner
        conf.channels = []
        conf.batched_commands = True
        conf.as_default_manager = True
        command = ["add", "-vv", "--no-self", "--group", group]
        for package in packages:
            command += ["--conda", package]
        if channel:
            command += ["--channel", channel]
        if runner:
            command += ["--runner", runner]
        else:
            runner = self.default_runner
        pdm(command, obj=project, strict=True)

        project.pyproject.reload()
        packages = [p.replace("'", "").replace('"', "") for p in packages]
        channels = set(p.split("::")[0] for p in packages if "::" in p)
        if channel:
            channels.add(channel)

        assert channels.issubset(conf.channels)
        assert conf.runner == runner
        cmd_order = ["create", "info", "list", "install"]
        assert conda.call_count == len(cmd_order)
        for (cmd,), kwargs in conda.call_args_list:
            assert cmd[0] == runner
            assert cmd[1] == cmd_order.pop(0)
        assert not cmd_order

        dependencies = project.get_dependencies(group)
        for package in packages:
            _package = package.split("::")[-1].split("=")[0]
            assert any(True for d in dependencies if _package in d)

    @pytest.mark.parametrize("packages", [["dep"], ["dep", "another-dep"], ["channel::dep"]])
    @pytest.mark.parametrize("batch_commands", [True, False])
    def test_remove(
        self,
        pdm,
        project,
        conda,
        conda_info,
        packages,
        runner,
        mock_conda_mapping,
        installed_packages,
        batch_commands,
        group,
    ):
        self.test_add(pdm, project, conda, packages, None, runner, mock_conda_mapping, installed_packages, group)
        conda.reset_mock()
        project.conda_config.batched_commands = batch_commands
        pdm(["remove", "--no-self", "-vv", "--group", group] + packages, obj=project, strict=True)

        python_packages = {p["name"] for p in PYTHON_REQUIREMENTS}
        packages_to_remove = set()
        for p in packages:
            pkg = PREFERRED_VERSIONS[p.split("::")[-1]]
            packages_to_remove.update(
                [d.split(" ")[0] for d in pkg["depends"] if not any(d.startswith(n) for n in python_packages)],
            )
            packages_to_remove.add(p)
        cmd_order = []
        if packages_to_remove:
            # get working set + get python packages
            cmd_order = (
                ["create", "list", "list"]
                + ["search" if runner == "conda" else "repoquery"] * (len({p["name"] for p in PYTHON_REQUIREMENTS}))
                + ["remove"] * (1 if batch_commands else len(packages_to_remove))
            )
        assert conda.call_count == len(cmd_order)

        dependencies = project.get_dependencies(group)
        for package in packages:
            _package = package.split("::")[-1].split("=")[0]
            assert _package not in dependencies

        packages = [p["name"] for p in conda_info]
        python_packages = [f"{p['name']}=={p['version']}={p['build']}" for p in PYTHON_REQUIREMENTS]
        for (cmd,), kwargs in conda.call_args_list:
            assert cmd[0] == (runner or self.default_runner)
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand in ("remove", "search", "repoquery"):
                name = next(filter(lambda x: not x.startswith("-") and x != "search", cmd[2:]))
                if cmd_subcommand == "remove":
                    assert name in packages
                    assert "-f" not in cmd
                elif cmd_subcommand in ("search", "repoquery"):
                    assert name in python_packages
        assert not cmd_order
