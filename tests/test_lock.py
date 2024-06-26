import itertools
from copy import copy

import pytest
from pdm.project.lockfile import FLAG_CROSS_PLATFORM, FLAG_INHERIT_METADATA
from pytest_mock import MockerFixture

from tests.conftest import PREFERRED_VERSIONS, PYTHON_PACKAGE, PYTHON_REQUIREMENTS


@pytest.fixture
def add_conflict() -> bool:
    return False


@pytest.fixture
def assert_all_responses_were_requested(add_conflict) -> bool:
    return not add_conflict


@pytest.mark.parametrize("runner", ["conda", "micromamba"])
@pytest.mark.parametrize("solver", ["conda", "libmamba"])
@pytest.mark.parametrize("group", ["default", "dev", "other"])
@pytest.mark.order(1)
class TestLock:
    @pytest.mark.parametrize(
        "add_conflict,auto_excludes,as_default_manager,num_missing_info_on_create",
        [
            [True, True, True, 1],
            [True, False, True, 1],
            [True, False, True, 0],
            [False, False, True, 2],
            [False, False, False, 0],
        ],
    )
    @pytest.mark.parametrize("overrides", [True, False])
    @pytest.mark.parametrize("direct_minimal_versions", [True, False])
    @pytest.mark.parametrize(
        "inherit_metadata,marker",
        [[True, 'python_version > "3.7"'], [True, None], [False, None]],
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
        num_missing_info_on_create,
        overrides,
        direct_minimal_versions,
        inherit_metadata,
        marker,
        auto_excludes,
        refresh=False,
    ):
        """Test lock command work as expected."""
        from pdm_conda.models.requirements import CondaRequirement

        python_dependencies = {c["name"] for c in PYTHON_REQUIREMENTS}
        conda_packages = [c for c in conda_info if c["name"] not in python_dependencies]
        python_packages = []
        config = project.conda_config
        config.runner = runner
        config.solver = solver
        config.as_default_manager = as_default_manager
        config.auto_excludes = auto_excludes

        name = conda_packages[-1]["name"]
        if marker:
            name += f";{marker}"
        packages = {group: [name]}
        if group != "default":
            if group != "dev":
                config.optional_dependencies = packages
            else:
                config.dev_dependencies = packages
        else:
            config.dependencies = packages[group]

        overrides_versions = {}
        if overrides:
            pkg = conda_packages[0]
            name = pkg["name"]
            if add_conflict:
                from pdm_conda.mapping import conda_to_pypi

                name = conda_to_pypi(name)
            overrides_versions = {name: pkg["version"]}
            project.pyproject.settings.setdefault("resolution", {}).setdefault("overrides", {}).update(
                overrides_versions,
            )
        # if add conflict then we expect resolver to first search package with PyPI and then use conda
        # because it's a dependency for another conda package
        if add_conflict:
            from pdm_conda.mapping import conda_to_pypi

            pkg = copy(conda_packages[0])
            name = conda_to_pypi(pkg["name"])
            extras = ["extra"]
            pkg["extras"] = extras
            # add a package that is only python
            if auto_excludes:
                python_packages.append("python-only-dep")
            project.pyproject._data.update(
                {
                    "project": {
                        "dependencies": [f"{name}[{','.join(extras)}]"] + python_packages,
                        "requires-python": project.pyproject.metadata["requires-python"],
                    },
                },
            )
            config.excludes = [name]
            # this will assert that this package is searched on pypi
            pypi([pkg], with_dependencies=True)
            for name in python_packages:
                pkg = next(filter(lambda x: x["name"] == name, PYTHON_REQUIREMENTS))
                pypi([pkg], with_dependencies=True)

        requirements = [
            r.conda_name
            for r in itertools.chain(*(deps.values() for deps in project.all_dependencies.values()))
            if isinstance(r, CondaRequirement) and r.name not in python_packages
        ]

        cmd = ["lock", "-vv", "-G", ":all"]
        if refresh:
            cmd.append("--refresh")
        if direct_minimal_versions:
            cmd += ["-S", "direct_minimal_versions"]
        if not inherit_metadata:
            cmd += ["-S", "no_inherit_metadata"]
        pdm(cmd, obj=project, strict=True)

        if auto_excludes:
            assert all(True for pkg in python_dependencies if pkg in config.excludes)

        lockfile = project.lockfile
        assert set(lockfile.groups) == {"default", group}
        assert FLAG_CROSS_PLATFORM not in lockfile.strategy
        if inherit_metadata:
            assert FLAG_INHERIT_METADATA in lockfile.strategy
        else:
            assert FLAG_INHERIT_METADATA not in lockfile.strategy
        packages = lockfile["package"]
        num_extras = 0
        for p in packages:
            name = p["name"]
            if inherit_metadata:
                assert p.get("groups", [])
                if p["name"] == conda_packages[-1]["name"]:
                    if marker:
                        assert p["marker"] == marker
                    else:
                        assert "marker" not in p
            else:
                assert not p.get("groups", [])
            if add_conflict and conda_mapping.get(name, name) == (pkg := conda_packages[0])["name"]:
                from pdm_conda.models.requirements import parse_conda_version

                assert p["version"] == parse_conda_version(pkg["version"])
                assert f"{name}=={p['version']}" in p["dependencies"]
                if "extras" in p:
                    num_extras += 1
            else:
                preferred_package = PREFERRED_VERSIONS[name]
                version = overrides_versions.get(name, preferred_package["version"])
                assert p["version"] == version
                if name not in python_packages:
                    assert p["build_string"] == preferred_package["build_string"]
                    assert p["build_number"] == preferred_package["build_number"]
                    assert p["conda_managed"]
                    assert preferred_package["channel"].endswith(p["channel"])
                    hashes = p["files"]
                    assert len(hashes) == 1
                    _hash = hashes[0]
                    assert "file" not in _hash
                    assert _hash["url"] == preferred_package["url"]
                    assert _hash["hash"] == f"md5:{preferred_package['md5']}"
                else:
                    assert all(k not in p for k in ("build_string", "build_number", "conda_managed", "channel"))

        if add_conflict:
            assert num_extras > 0
        search_command = "search" if runner == "conda" else "repoquery"
        packages_to_search = {PYTHON_PACKAGE["name"], *requirements}
        cmd_order = (
            ["create"] * (len(python_packages) + 1)
            + [search_command] * (0 if runner == "micromamba" else num_missing_info_on_create)
            + ["info"]
            + ["create"] * (1 if refresh else 0)
        )

        assert conda.call_count == len(cmd_order)
        for (cmd,), _ in conda.call_args_list:
            assert cmd[0] == runner
            assert (cmd_subcommand := cmd[1]) == cmd_order.pop(0)
            if cmd_subcommand == "create":
                # assert packaged is search
                for req in packages_to_search:
                    assert any(True for arg in cmd if req in arg)

        assert not cmd_order
        return project.lockfile

    @pytest.mark.parametrize("inherit_metadata", [True, False])
    @pytest.mark.parametrize("add_conflict", [True])
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
        inherit_metadata,
        add_conflict,
    ):
        old_lockfile = self.test_lock(
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
            True,
            0,
            False,
            marker=None,
            direct_minimal_versions=False,
            auto_excludes=False,
            inherit_metadata=inherit_metadata,
        )
        lockfile = self.test_lock(
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
            True,
            0,
            False,
            marker=None,
            refresh=True,
            direct_minimal_versions=False,
            auto_excludes=False,
            inherit_metadata=inherit_metadata,
        )
        assert old_lockfile == lockfile

    def test_lock_inactive(
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
    ):
        """Test lock command work as expected."""

        python_dependencies = {c["name"] for c in PYTHON_REQUIREMENTS}
        conda_packages = [c for c in conda_info if c["name"] not in python_dependencies]
        config = project.conda_config
        config.runner = runner
        config.solver = solver
        assert config.is_initialized
        project.pyproject._data.update({"tool": {"pdm": {"conda": {"active": False}}}})
        assert not config.active
        assert not config.is_initialized

        from pdm_conda.mapping import conda_to_pypi

        name = conda_packages[-1]["name"]
        packages = {group: [name]}
        if group != "default":
            if group != "dev":
                config.optional_dependencies = packages
            else:
                config.dev_dependencies = packages
        else:
            config.dependencies = packages[group]

        pkg = copy(conda_packages[1])
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

        cmd = ["lock", "-vv", "-G", ":all"]
        pdm(cmd, obj=project, strict=True)
        conda.assert_not_called()


class TestGroupsLock:
    def test_lock_prod_dev(
        self,
        pdm,
        project,
        conda,
        conda_info,
        mock_conda_mapping,
    ):
        from pdm_conda.models.requirements import parse_requirement

        python_dependencies = {c["name"] for c in PYTHON_REQUIREMENTS}
        conda_packages = [c for c in conda_info if c["name"] not in python_dependencies]
        project.add_dependencies(
            {conda_packages[0]["name"]: parse_requirement(conda_packages[0]["name"])},
            to_group="dev",
            dev=True,
            show_message=False,
            write=False,
        )
        project.conda_config.as_default_manager = True
        project.conda_config.runner = "micromamba"

        cmd = ["lock", "-vv", "-G", ":all"]
        pdm(cmd + ["--dev"], obj=project, strict=True)

        dev_lock = set(project.lockfile.groups)
        assert FLAG_CROSS_PLATFORM not in project.lockfile.strategy

        pdm(cmd + ["--prod"], obj=project, strict=True)

        prod_lock = set(project.lockfile.groups)
        dev_lock.remove("dev")
        assert dev_lock == prod_lock
        assert FLAG_CROSS_PLATFORM not in project.lockfile.strategy

    @pytest.mark.parametrize("use_default", [True, False])
    @pytest.mark.parametrize("use_dev", [True, False])
    def test_equal_groups_resolution(self, pdm, project, use_default, use_dev, mocker: MockerFixture):
        from pdm_conda.models.requirements import parse_requirement

        dev_groups = {f"group_{i}": [f"dep_{i}"] for i in range(3)}
        optional_groups = {f"op_group_{i}": [f"dep_{i}"] for i in range(3)}

        for resolution, is_dev in ((dev_groups, True), (optional_groups, False)):
            for group, deps in resolution.items():
                project.add_dependencies(
                    {dep: parse_requirement(dep) for dep in deps},
                    to_group=group,
                    dev=is_dev,
                    show_message=False,
                    write=False,
                )
        resolutions = [
            ({"default"} if use_default else set()) | (set(dev_groups) if use_dev else set()) | set(optional_groups),
        ]

        for initialized in (True, False):
            mocker.patch.object(project.conda_config, "_initialized", initialized)

            assert project.conda_config.is_initialized == initialized
            handle = mocker.patch("pdm.cli.commands.lock.actions.do_lock")
            cmd = ["lock", "-G", ":all"]
            if not use_default:
                cmd.append("--no-default")

            pdm(cmd, obj=project, strict=True)
            handle.assert_called_once()

            resolutions.append(set(handle.call_args[1]["groups"]))


class TestLockOverrides:
    @pytest.mark.parametrize("cross_platform", [True, False])
    @pytest.mark.parametrize("initialized", [True, False])
    def test_no_cross_platform(self, pdm, project, cross_platform, initialized, mocker: MockerFixture):
        mocker.patch.object(project.conda_config, "_initialized", initialized)

        assert project.conda_config.is_initialized == initialized
        handle = mocker.patch("pdm_conda.cli.commands.lock.BaseCommand.handle")
        cmd = ["lock", "-S", ("" if cross_platform else "no_") + "cross_platform"]
        pdm(cmd, obj=project, strict=True)
        handle.assert_called_once()

        strategy = handle.call_args[1]["options"].strategy_change
        assert ("cross_platform" in strategy) == (cross_platform and not initialized)
        assert ("no_cross_platform" in strategy) == (initialized or not cross_platform)
