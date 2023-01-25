import pytest

DEPENDENCIES = dict(
    argnames=["dependencies", "conda_dependencies"],
    argvalues=[
        (["pytest"], ["pytest-cov"]),
        (["pytest>=3.1"], ["pytest-conda"]),
        (["pytest[extra]"], ["pytest-conda"]),
        (["pytest"], ["pytest-conda[extra]"]),
        (["pytest>=3.1"], ["pytest-conda==52"]),
        ([], ["conda-channel::pytest-conda"]),
        (["pytest"], []),
        ([], ["pytest-conda>=1.*"]),
        ([], ["pytest-conda>1.*"]),
    ],
    ids=[
        "different pkgs",
        "pypi version override",
        "conda extras override",
        "conda no extras",
        "conda version override",
        "conda channel",
        "only pypi",
        "star >= specifier",
        "star > specifier",
    ],
)
CONDA_MAPPING = dict(
    argnames="conda_mapping",
    argvalues=[{"pytest": "pytest-conda"}],
    ids=["use conda mapping"],
)
GROUPS = dict(argnames="group", argvalues=["default", "dev", "optional"])


class TestProject:
    def _parse_requirements(
        self,
        dependencies,
        conda_dependencies,
        as_default_manager=False,
    ):
        from pdm_conda.mapping import pypi_to_conda
        from pdm_conda.models.requirements import CondaRequirement, parse_requirement

        requirements = dict()
        for d in dependencies:
            if as_default_manager:
                d = f"conda:{d}"
            r = parse_requirement(d)
            if as_default_manager:
                r.name = pypi_to_conda(r.name)
            requirements[r.identify()] = r
        for d in conda_dependencies:
            d = d.strip()
            r = parse_requirement(f"conda:{d}")
            if "::" in d:
                assert d.endswith(r.as_line())
            else:
                assert d.startswith(r.as_line())
            assert isinstance(r, CondaRequirement)
            assert not r.extras
            if "::" in d:
                assert r.channel == d.split("::")[0]
            pypi_req = next((v for v in requirements.values() if v.conda_name == r.conda_name), None)
            if pypi_req is not None:
                requirements.pop(pypi_req.identify())
                if not r.specifier:
                    r.specifier = pypi_req.specifier
            requirements[r.identify()] = r
        return requirements

    @pytest.mark.parametrize(**DEPENDENCIES)
    @pytest.mark.parametrize(**GROUPS)
    @pytest.mark.parametrize(**CONDA_MAPPING)
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
        """
        Test get project dependencies with conda dependencies and correct parse requirements
        """

        def dependencies_conf(dependencies, group):
            if group == "default":
                return {"dependencies": dependencies}
            else:
                return {f"{group}-dependencies": {"dev": dependencies}}

        def project_conf(dependencies, conda_dependencies, group, as_default_manager):
            dependencies, conda_dependencies = dependencies_conf(dependencies, group), dependencies_conf(
                conda_dependencies,
                group,
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
                conf["tool"]["pdm"].setdefault("conda", dict())["as-default-manager"] = True

            return conf

        project.pyproject._data.update(project_conf(dependencies, conda_dependencies, group, as_default_manager))

        if group != "default":
            group = "dev"

        requirements = self._parse_requirements(
            dependencies,
            conda_dependencies,
            as_default_manager=as_default_manager,
        )
        project_requirements = project.get_dependencies(group)
        for name, req in project_requirements.items():
            conda_req = requirements[req.conda_name]
            assert conda_req == req
            assert isinstance(req, type(conda_req))
        assert all("[" not in k for k in project_requirements)

    @pytest.mark.parametrize(**DEPENDENCIES)
    @pytest.mark.parametrize(**GROUPS)
    @pytest.mark.parametrize(**CONDA_MAPPING)
    def test_add_dependencies(
        self,
        project,
        dependencies,
        conda_dependencies,
        group,
        mock_conda_mapping,
    ):
        requirements = self._parse_requirements(dependencies, conda_dependencies)

        group_name = group if group == "default" else "dev"
        dev = group == "dev"
        project.add_dependencies(requirements, to_group=group_name, dev=dev)
        project_requirements = project.get_dependencies(group_name)
        for name, req in project_requirements.items():
            assert req == requirements[name]
            assert isinstance(req, type(requirements[name]))

        from pdm_conda.mapping import conda_to_pypi

        if conda_dependencies:
            _dependencies, _ = project.get_pyproject_dependencies(group_name, dev)
            _conda_dependencies = project.get_conda_pyproject_dependencies(group_name, dev)
            for d in conda_dependencies:
                asserted = 0
                d = d.split("[")[0].split("=")[0].split(">")[0].split("::")[-1]
                for c in (_conda_dependencies, _dependencies):
                    for r in c:
                        if d in r or conda_to_pypi(d) in r:
                            asserted += 1
                            break
                assert asserted == len(conda_dependencies) * (2 if requirements[d].is_python_package else 1)
        assert all("[" not in k for k in project.get_dependencies(group_name))
