import itertools
from typing import cast

import pytest

from tests.conftest import CONDA_REQUIREMENTS, PREFERRED_VERSIONS, PYTHON_REQUIREMENTS


@pytest.mark.usefixtures("fake_python")
@pytest.mark.parametrize("runner", [None, "micromamba", "conda"])
@pytest.mark.parametrize("group", ["default", "other"])
@pytest.mark.usefixtures("working_set")
class TestAddRemove:
    default_runner = "micromamba"

    @pytest.mark.parametrize(
        "packages",
        [
            ["'dep'"],
            ["'another-dep==1!0.1gg'"],
            ["\"dep ; python_version > '3.5'\"", "another-dep"],
            ["'channel::dep'", "another-dep"],
        ],
    )
    @pytest.mark.parametrize("channel", [None, "another_channel"])
    @pytest.mark.parametrize("excludes", [None, ["excluded-dep1", "excluded-dep2"], "excluded-dep1,excluded-dep2"])
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
        excludes,
        group,
    ):
        """Test `add` command work as expected."""
        from pdm_conda.project import CondaProject

        project = cast(CondaProject, project)
        conf = project.conda_config
        conf.runner = runner or self.default_runner
        conf.channels = []
        conf.batched_commands = True
        command = ["add", "-vv", "--no-self", "--group", group, "--conda-as-default-manager"]
        for package in packages:
            command += ["--conda", package]
        if channel:
            command += ["--channel" if runner == "conda" else "-c", channel]
        if runner:
            command += ["--runner", runner]
        else:
            runner = self.default_runner
        if excludes:
            if not isinstance(excludes, list):
                excludes = [excludes]
            for pkg in excludes:
                command += ["-ce", pkg]
            excludes = list(itertools.chain.from_iterable(pkg.split(",") for pkg in excludes))
        else:
            excludes = []
        pdm(command, obj=project, strict=True)

        project.pyproject.reload()
        packages = [p.replace("'", "").replace('"', "") for p in packages]
        channels = set(p.split("::")[0] for p in packages if "::" in p)
        if channel:
            channels.add(channel)

        assert channels.issubset(conf.channels)
        assert set(conf.excludes) == set(excludes)
        assert conf.runner == runner
        assert conf.as_default_manager
        assert set(project.lockfile.groups) == {group, "default"}
        cmd_order = ["create", "info", "list", "install"]
        assert conda.call_count == len(cmd_order)
        for (cmd,), kwargs in conda.call_args_list:
            assert cmd[0] == runner
            assert cmd[1] == cmd_order.pop(0)
        assert not cmd_order

        dependencies = project.get_dependencies(group)
        for package in packages:
            pkg = PREFERRED_VERSIONS[package.split("::")[-1].split("=")[0].split(";")[0].strip()]
            assert (dep := dependencies.get(pkg["name"], None)) is not None
            allowed_versions = [pkg["version"]]
            if pkg["version"].endswith(".0"):
                allowed_versions.append(f">={pkg['version'][:-2]}")
            assert any(v in dep.as_line() for v in allowed_versions)

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
        self.test_add(
            pdm,
            project,
            conda,
            packages,
            None,
            runner,
            mock_conda_mapping,
            installed_packages,
            group=group,
            excludes=[],
        )
        conda.reset_mock()
        project.conda_config.batched_commands = batch_commands
        pdm(["remove", "--no-self", "-vv", "--group", group] + packages, obj=project, strict=True)

        python_packages = {p["name"] for p in PYTHON_REQUIREMENTS if not p["python_only"]}
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
            cmd_order = ["create", "list", "list"]
            if project.conda_config.runner in ("mamba", "micromamba") or project.conda_config.solver == "libmamba":
                cmd_order.append("create")
            else:
                num_searches = len(python_packages)
                cmd_order += ["search" if runner == "conda" else "repoquery"] * num_searches
            cmd_order += ["remove"] * (1 if batch_commands else len(packages_to_remove))
        assert conda.call_count == len(cmd_order)

        dependencies = project.get_dependencies(group)
        for package in packages:
            _package = package.split("::")[-1].split("=")[0]
            assert _package not in dependencies

        packages = [p["name"] for p in conda_info]
        python_packages = [
            f"{p['name']}=={p['version']}={p['build']}"
            for p in PYTHON_REQUIREMENTS + CONDA_REQUIREMENTS
            if not p["python_only"]
        ]
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
