import itertools

import pytest
from pytest_mock import MockerFixture

from tests.conftest import (
    CONDA_INFO,
    CONDA_MAPPING,
    PREFERRED_VERSIONS,
    PYTHON_PACKAGE,
    PYTHON_REQUIREMENTS,
)


@pytest.mark.parametrize("runner", ["conda", "micromamba"])
@pytest.mark.parametrize("solver", ["conda", "libmamba"])
@pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
@pytest.mark.parametrize("conda_info", CONDA_INFO)
@pytest.mark.parametrize("group", ["default", "dev", "other"])
class TestLock:
    @pytest.mark.parametrize(
        "add_conflict,as_default_manager,num_remove_fetch",
        [[True, True, 1], [True, True, 0], [False, True, 2], [False, False, 0]],
    )
    def test_lock(
        self,
        pdm,
        project,
        conda,
        conda_info,
        runner,
        solver,
        pypi,
        group,
        add_conflict,
        conda_mapping,
        mock_conda_mapping,
        as_default_manager,
        num_remove_fetch,
        refresh=False,
    ):
        """
        Test lock command work as expected
        """
        from pdm_conda.models.requirements import CondaRequirement

        python_dependencies = {c["name"] for c in PYTHON_REQUIREMENTS}
        conda_packages = [c for c in conda_info if c["name"] not in python_dependencies]
        config = project.conda_config
        config.runner = runner
        config.solver = solver
        config.as_default_manager = as_default_manager

        packages = {group: [conda_packages[-1]["name"]]}
        if group != "default":
            if group != "dev":
                config.optional_dependencies = packages
            else:
                config.dev_dependencies = packages
        else:
            packages = packages[group]
            config.dependencies = packages
        # if add conflict then we expect resolver to first search package with PyPI and then use conda
        # because it's a dependency for another conda package
        if add_conflict:
            from pdm_conda.mapping import conda_to_pypi

            pkg = conda_packages[0]
            name = conda_to_pypi(pkg["name"])
            project.pyproject._data.update(
                {
                    "project": {
                        "dependencies": [name],
                        "requires-python": project.pyproject.metadata["requires-python"],
                    },
                },
            )
            config.excludes = [name]
            # this will assert that this package is searched on pypi
            pypi([pkg], with_dependencies=True)

        requirements = [
            r.conda_name
            for r in itertools.chain(*(deps.values() for deps in project.all_dependencies.values()))
            if isinstance(r, CondaRequirement)
        ]

        cmd = ["lock", "-vv", "-G", ":all"]
        if refresh:
            cmd.append("--refresh")
        pdm(cmd, obj=project, strict=True)
        search_command = "search" if runner == "conda" else "repoquery"
        cmd_order = ["create"] + [search_command] * (0 if runner == "micromamba" else num_remove_fetch) + ["info"]
        packages_to_search = {PYTHON_PACKAGE["name"], *requirements}

        assert conda.call_count == len(cmd_order)
        for (cmd,), kwargs in conda.call_args_list:
            assert cmd[0] == runner
            assert (cmd_subcommand := cmd[1]) == cmd_order.pop(0)
            if cmd_subcommand == "create":
                # assert packaged is search
                for req in packages_to_search:
                    assert any(True for arg in cmd if req in arg)

        assert not cmd_order
        lockfile = project.lockfile
        packages = lockfile["package"]
        hashes = lockfile["metadata"]["files"]
        for p in packages:
            name = p["name"]
            if add_conflict and conda_mapping.get(name, name) == (pkg := conda_packages[0])["name"]:
                from pdm_conda.models.requirements import parse_conda_version

                assert p["version"] == parse_conda_version(pkg["version"])
            else:
                preferred_package = PREFERRED_VERSIONS[name]
                version = preferred_package["version"]
                assert p["version"] == version
                assert p["build_string"] == preferred_package["build_string"]
                assert p["build_number"] == preferred_package["build_number"]
                assert p["conda_managed"]
                assert preferred_package["channel"].endswith(p["channel"])
                _hash = hashes[f"{name} {version}"]
                assert len(_hash) == 1
                _hash = _hash[0]
                assert _hash["url"] == preferred_package["url"]
                assert _hash["hash"] == f"md5:{preferred_package['md5']}"

    @pytest.mark.parametrize("num_remove_fetch", [0])
    def test_lock_refresh(
        self,
        pdm,
        project,
        conda,
        conda_info,
        runner,
        solver,
        pypi,
        group,
        conda_mapping,
        mock_conda_mapping,
        num_remove_fetch,
    ):
        self.test_lock(
            pdm,
            project,
            conda,
            conda_info,
            runner,
            solver,
            pypi,
            group,
            False,
            conda_mapping,
            mock_conda_mapping,
            True,
            num_remove_fetch,
        )
        self.test_lock(
            pdm,
            project,
            conda,
            conda_info,
            runner,
            solver,
            pypi,
            group,
            False,
            conda_mapping,
            mock_conda_mapping,
            True,
            num_remove_fetch,
            refresh=True,
        )


class TestLockOverrides:
    @pytest.mark.parametrize("cross_platform", [True, False])
    @pytest.mark.parametrize("initialized", [True, False])
    def test_no_cross_platform(self, pdm, project, cross_platform, initialized, mocker: MockerFixture):
        mocker.patch.object(project.conda_config, "_initialized", initialized)

        assert project.conda_config.is_initialized == initialized
        handle = mocker.patch("pdm_conda.cli.commands.lock.BaseCommand.handle")
        cmd = ["lock"]
        if not cross_platform:
            cmd.append("--no-cross-platform")
        pdm(cmd, obj=project, strict=True)
        handle.assert_called_once()

        assert handle.call_args[1]["options"].cross_platform == (False if initialized else cross_platform)
