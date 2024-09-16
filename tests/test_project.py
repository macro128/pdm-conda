import re

import pytest

REQUIREMENTS_TO_TEST = {
    "different pkgs": (["pytest"], ["pytest-cov"]),
    "pypi version inherit": (["pytest>=3.1"], ["pytest-conda"]),
    "conda extras override": (["pytest[extra]"], ["pytest-conda"]),
    "conda extras": (["pytest"], ["pytest-conda[extra]"]),
    "conda version override": (["pytest>=3.1"], ["pytest-conda==52"]),
    "conda channel": ([], ["conda-channel::pytest-conda"]),
    "conda channel with platform": ([], ["conda-channel/arch1::pytest-conda"]),
    "only pypi": (["pytest"], []),
    "star >= specifier": ([], ["pytest-conda>=1.*"]),
    "star > specifier": ([], ["pytest-conda>1.*"]),
    "~= specifier": ([], ["pytest-conda~=1.0.0"]),
    "~= star specifier": ([], ["pytest-conda~=1.*"]),
    "= specifier": ([], ["pytest-conda=1"]),
    "conda with build string": ([], ["pytest-conda==1.0=build_string"]),
    "pypi markers inherit": (["pytest; python_version >= '3.6'"], ["pytest-conda"]),
    "conda with markers": (["pytest"], ["pytest-conda; python_version >= '3.6'"]),
    "virtual package": ([], ["__virtual_package"]),
    "conda with underscore": ([], ["_package==1.0.0"]),
}
DEPENDENCIES = {
    "argnames": ["dependencies", "conda_dependencies"],
    "argvalues": list(REQUIREMENTS_TO_TEST.values()),
    "ids": list(REQUIREMENTS_TO_TEST.keys()),
}
CONDA_MAPPING = {
    "argnames": "conda_mapping",
    "argvalues": [{"pytest": "pytest-conda"}],
    "ids": ["use conda mapping"],
}
GROUPS = {"argnames": "group", "argvalues": ["default", "dev", "optional"]}


@pytest.mark.parametrize(**CONDA_MAPPING)
class TestProject:
    def _parse_requirements(
        self,
        dependencies,
        conda_dependencies,
        as_default_manager=False,
    ):
        from pdm_conda.mapping import pypi_to_conda
        from pdm_conda.models.requirements import CondaRequirement, CondaVirtualPackageRequirement, parse_requirement

        requirements = []
        for d in dependencies:
            if as_default_manager:
                d = f"conda:{d}"
            r = parse_requirement(d)
            if as_default_manager:
                r.name = pypi_to_conda(r.name)
            requirements.append(r)
        for d in conda_dependencies:
            d = d.strip().replace("'", '"')
            r = parse_requirement(f"conda:{d}")
            if "::" in d:
                assert d.endswith(r.as_line())
            elif re.search(r"\w=\d", d):
                assert r.as_line() == d.replace("=", "==") + ".*"
            else:
                assert d.startswith(r.as_line())
            if d.startswith("__"):
                assert isinstance(r, CondaVirtualPackageRequirement)
            assert isinstance(r, CondaRequirement)
            assert r.extras if "[" in d else not r.extras
            assert r.marker if ";" in d else not r.marker
            if "::" in d:
                assert r.channel == d.split("::")[0]
            pypi_req_idx = next((i for i, v in enumerate(requirements) if v.conda_name == r.conda_name), None)
            if pypi_req_idx is not None:
                pypi_req = requirements[pypi_req_idx]
                if not r.specifier:
                    r.specifier = pypi_req.specifier
                if pypi_req.marker:
                    r.marker = pypi_req.marker
                if pypi_req.extras:
                    r.extras = pypi_req.extras
                requirements[pypi_req_idx] = r
            else:
                requirements.append(r)
        return requirements

    @pytest.mark.parametrize(**DEPENDENCIES)
    @pytest.mark.parametrize(**GROUPS)
    @pytest.mark.parametrize("as_default_manager", [False, True], ids=["", "as_default_manager"])
    def test_get_dependencies(
        self,
        project,
        dependencies,
        conda_dependencies,
        group,
        as_default_manager,
        mock_conda_mapping,
    ):
        """Test get project dependencies with conda dependencies and correct parse requirements."""

        def dependencies_conf(dependencies, group):
            if group == "default":
                return {"dependencies": dependencies}
            return {f"{group}-dependencies": {"dev": dependencies}}

        def project_conf(dependencies, conda_dependencies, group, as_default_manager):
            dependencies, conda_dependencies = (
                dependencies_conf(dependencies, group),
                dependencies_conf(
                    conda_dependencies,
                    group,
                ),
            )

            if group == "dev":
                dependencies.update({"conda": conda_dependencies})
                conf = {"tool": {"pdm": dependencies}}
            else:
                conf = {
                    "project": dependencies,
                    "tool": {
                        "pdm": {"conda": conda_dependencies},
                    },
                }
            if as_default_manager:
                conf["tool"]["pdm"].setdefault("conda", {})["as-default-manager"] = True

            return conf

        project.pyproject._data.update(project_conf(dependencies, conda_dependencies, group, as_default_manager))

        if group != "default":
            group = "dev"

        requirements = self._parse_requirements(
            dependencies,
            conda_dependencies,
            as_default_manager=as_default_manager,
        )

        for project_requirements in (project.get_dependencies(group), project.all_dependencies[group]):
            for req in project_requirements:
                conda_req = next(r for r in requirements if r.conda_name == req.conda_name)
                assert conda_req == req
                assert isinstance(req, type(conda_req))

    @pytest.mark.parametrize(**DEPENDENCIES)
    @pytest.mark.parametrize(**GROUPS)
    @pytest.mark.parametrize("as_default_manager", [True], ids=["as_default_manager"])
    def test_add_dependencies(
        self,
        project,
        dependencies,
        conda_dependencies,
        group,
        mock_conda_mapping,
        as_default_manager,
    ):
        from pdm_conda.mapping import conda_to_pypi
        from pdm_conda.models.requirements import CondaRequirement, CondaVirtualPackageRequirement, strip_extras

        project.conda_config.as_default_manager = as_default_manager
        requirements = self._parse_requirements(dependencies, conda_dependencies, as_default_manager=as_default_manager)
        requirements = [r for r in requirements if not isinstance(r, CondaVirtualPackageRequirement)]
        group_name = group if group == "default" else "dev"
        dev = group == "dev"
        project.add_dependencies(requirements, to_group=group_name, dev=dev)
        project_requirements = project.get_dependencies(group_name)
        requirement_names = [r.conda_name for r in requirements]
        for req in requirements:
            name = req.conda_name
            assert req == project_requirements[requirement_names.index(name)]
            if isinstance(req, CondaRequirement) and req.is_python_package:
                named_req = req.as_named_requirement()
                if named_req.name != req.name:
                    assert named_req not in requirement_names

        if conda_dependencies:
            _dependencies, _ = project.use_pyproject_dependencies(group_name, dev)
            _conda_dependencies = project.get_conda_pyproject_dependencies(group_name, dev)
            for dep in conda_dependencies:
                if dep.startswith("__"):
                    continue
                asserted = 0
                dep, _ = strip_extras(
                    dep.split(";")[0].split("=")[0].split(">")[0].split("~")[0].split("::")[-1].strip(),
                )
                python_dep = conda_to_pypi(dep)
                for c in (_conda_dependencies, _dependencies):
                    for r in c:
                        if dep in r or python_dep in r:
                            asserted += 1
                            break
                req = next((r for r in requirements if r.conda_name == dep or r.name.startswith(f"{dep}[")), None)
                assert req is not None

                num_assertions = 1
                # if not python package then it should only be in conda_dependencies
                if not req.is_python_package:
                    num_assertions = 1
                # if conda default manager but req has conda info then it should be in both
                elif as_default_manager and req.is_python_package and (req.build_string or req.channel):
                    num_assertions = 2
                assert asserted == num_assertions

    @pytest.mark.parametrize(
        "config_name,config_value,must_be_different",
        [
            ["channels", ["other"], True],
            ["batched_commands", True, False],
            ["runner", "micromamba", False],
            ["solver", "libmamba", False],
            ["installation_method", "copy", False],
            ["as_default_manager", True, True],
            ["dependencies", ["package"], True],
            ["excludes", ["package"], True],
            ["dev_dependencies", {"dev": ["package"]}, True],
            ["optional_dependencies", {"other": ["package"]}, True],
        ],
    )
    def test_pyproject_hash(self, project, config_name, config_value, must_be_different, mock_conda_mapping):
        original_hash = project.pyproject.content_hash()
        config = project.conda_config
        original_value = getattr(config, config_name)
        assert original_value != config_value
        setattr(config, config_name, config_value)
        if must_be_different:
            assert original_hash != project.pyproject.content_hash()
        else:
            assert original_hash == project.pyproject.content_hash()
        setattr(config, config_name, original_value)
        assert original_hash == project.pyproject.content_hash()


@pytest.mark.usefixtures("working_set")
class TestProjectProviders:
    @pytest.mark.parametrize("strategy", ["all", "reuse", "eager", "reuse-installed"])
    def test_provider(self, project, strategy, conda):
        from pdm_conda.resolver.providers import (
            CondaBaseProvider,
            CondaEagerUpdateProvider,
            CondaReuseInstalledProvider,
            CondaReusePinProvider,
        )

        provider = {
            "all": CondaBaseProvider,
            "reuse": CondaReusePinProvider,
            "eager": CondaEagerUpdateProvider,
            "reuse-installed": CondaReuseInstalledProvider,
        }
        assert isinstance(project.get_provider(strategy=strategy), provider[strategy])
