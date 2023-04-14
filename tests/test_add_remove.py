from typing import cast

import pytest

from tests.conftest import (
    CONDA_INFO,
    CONDA_MAPPING,
    PREFERRED_VERSIONS,
    PYTHON_REQUIREMENTS,
)


@pytest.mark.parametrize("conda_response", CONDA_INFO)
@pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
@pytest.mark.parametrize("runner", [None, "micromamba", "conda"])
class TestAddRemove:
    default_runner = "micromamba"

    @pytest.mark.parametrize(
        "packages",
        [["'dep'"], ["'another-dep==1!0.1gg'"], ['"dep"', "another-dep"], ["'channel::dep'", "another-dep"]],
    )
    @pytest.mark.parametrize("channel", [None, "another_channel"])
    def test_add(self, pdm, project, conda, packages, channel, runner, mock_conda_mapping, installed_packages):
        """
        Test `add` command work as expected
        """
        from pdm_conda.project import CondaProject

        project = cast(CondaProject, project)
        conf = project.conda_config
        conf.runner = runner or self.default_runner
        conf.channels = []
        command = ["add", "-v", "--no-self"]
        for package in packages:
            command.extend(["--conda", package])
        if channel:
            command += ["--channel", channel]
        if runner:
            command += ["--runner", runner]
        else:
            runner = self.default_runner
        num_commands = 3  # add conda info, list and python package
        packages_names = {p.split("::")[-1].split("==")[0].replace("'", "").replace('"', "") for p in packages}
        to_search = set()
        for name in packages_names:
            if name not in to_search:
                pkg = PREFERRED_VERSIONS[name]
                to_search.update([d for d in pkg["depends"] if not d.startswith("python ")])
                to_search.add(name)
        if to_search:
            num_commands += (
                len(to_search)
                + len(
                    {p.split(" ")[0] for p in to_search} - {p["name"] for p in installed_packages},
                )
                + 1
            )

        pdm(command, obj=project, strict=True)

        project.pyproject.reload()
        packages = [p.replace("'", "").replace('"', "") for p in packages]
        channels = set(p.split("::")[0] for p in packages if "::" in p)
        if channel:
            channels.add(channel)

        assert channels.issubset(conf.channels)
        assert conf.runner == runner
        assert conda.call_count == num_commands

        dependencies = project.get_conda_pyproject_dependencies("default")
        for package in packages:
            _package = package.split("::")[-1]
            assert any(True for d in dependencies if _package in d)

    @pytest.mark.parametrize("packages", [["dep"], ["dep", "another-dep"], ["channel::dep"]])
    def test_remove(
        self,
        pdm,
        project,
        conda,
        conda_response,
        packages,
        runner,
        mock_conda_mapping,
        installed_packages,
    ):
        self.test_add(pdm, project, conda, packages, None, runner, mock_conda_mapping, installed_packages)
        conda.reset_mock()
        pdm(["remove", "--no-self", "-vv"] + packages, obj=project, strict=True)

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
                ["list", "list"]
                + ["search" if runner == "conda" else "repoquery"] * (len({p["name"] for p in PYTHON_REQUIREMENTS}) - 1)
                + ["remove"] * len(packages_to_remove)
            )
        assert conda.call_count == len(cmd_order)
        packages = [p["name"] for p in conda_response]
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
