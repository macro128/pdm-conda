import itertools

import pytest

from tests.conftest import (
    CONDA_INFO,
    CONDA_MAPPING,
    PYTHON_PACKAGE,
    PYTHON_REQUIREMENTS,
    PYTHON_VERSION,
)


@pytest.mark.parametrize("empty_conda_list", [False])
@pytest.mark.parametrize("runner", ["conda", "micromamba"])
@pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
@pytest.mark.parametrize("conda_response", CONDA_INFO)
@pytest.mark.parametrize("group", ["default", "dev", "other"])
class TestLock:
    @pytest.mark.parametrize("add_conflict", [True, False])
    def test_lock(
        self,
        pdm,
        project,
        conda,
        conda_response,
        runner,
        pypi,
        group,
        add_conflict,
        mock_conda_mapping,
        refresh=False,
    ):
        """
        Test lock command work as expected
        """
        from pdm_conda.models.requirements import CondaRequirement

        python_dependencies = {c["name"] for c in PYTHON_REQUIREMENTS}
        conda_packages = [c for c in conda_response if c["name"] not in python_dependencies]
        config = project.conda_config
        config.runner = runner

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
            project.pyproject._data.update(
                {
                    "project": {"dependencies": [conda_packages[0]["name"]], "requires-python": f"=={PYTHON_VERSION}"},
                },
            )
            # this will assert that this package is searched on pypi
            pypi([conda_packages[0]], with_dependencies=True)

        requirements = [
            r.as_line(conda_compatible=True, with_build_string=True)
            for r in itertools.chain(*(deps.values() for deps in project.all_dependencies.values()))
            if isinstance(r, CondaRequirement)
        ]

        cmd = ["lock", "-v"]
        if refresh:
            cmd.append("--refresh")
        result = pdm(cmd, obj=project)
        assert result.exception is None
        # first subcommands are for python dependency and virtual packages
        cmd_order = ["list", "info"]
        packages_to_search = {
            f"{PYTHON_PACKAGE['name']}=={PYTHON_PACKAGE['version']}={PYTHON_PACKAGE['build']}",
            *requirements,
        }
        for c in conda_packages:
            for d in c["depends"]:
                if not d.startswith("python "):
                    packages_to_search.add(d.replace(" ", "").split("|")[0])

        if packages_to_search:
            cmd_order.extend(["search" if runner == "conda" else "repoquery"] * len(packages_to_search))

        assert conda.call_count == len(cmd_order)
        for (cmd,), kwargs in conda.call_args_list:
            assert cmd[0] == runner
            assert (cmd_subcommand := cmd[1]) == cmd_order.pop(0)
            if cmd_subcommand == "search":
                # assert packaged is search
                assert next(filter(lambda x: not x.startswith("-"), cmd[2:])) in packages_to_search

        packages_to_search = {p.split("=")[0] for p in packages_to_search}
        assert not cmd_order
        lockfile = project.lockfile
        packages = lockfile["package"]
        for p in packages:
            assert p["name"] in packages_to_search

    def test_lock_refresh(self, pdm, project, conda, conda_response, runner, pypi, group, mock_conda_mapping):
        self.test_lock(pdm, project, conda, conda_response, runner, pypi, group, False, mock_conda_mapping)
        self.test_lock(
            pdm,
            project,
            conda,
            conda_response,
            runner,
            pypi,
            group,
            False,
            mock_conda_mapping,
            refresh=True,
        )
