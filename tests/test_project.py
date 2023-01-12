import re

import pytest

DEPENDENCIES = dict(
    argnames=["dependencies", "conda_dependencies"],
    argvalues=[
        (["pytest"], ["pytest-cov"]),
        (["pytest>=3.1"], ["pytest"]),
        (["pytest[extra]"], ["pytest"]),
        (["pytest"], ["pytest[extra]"]),
        (["pytest>=3.1"], ["pytest==52"]),
        ([], ["conda-channel::pytest"]),
        (["pytest"], []),
        ([], ["pytest>=1.*"]),
    ],
    ids=[
        "different pkgs",
        "pypi version override",
        "conda extras override",
        "conda no extras",
        "conda version override",
        "conda channel",
        "only pypi",
        "star greater specifier",
    ],
)
GROUPS = dict(argnames="group", argvalues=["default", "dev", "optional"])


class TestProject:
    def _parse_requirements(self, dependencies, conda_dependencies, as_default_manager=False):
        from pdm_conda.models.requirements import CondaRequirement, parse_requirement

        requirements = dict()
        for d in dependencies:
            if as_default_manager:
                if "[" in d:
                    d = d.split("[")[0]
                d = f"conda:{d}"
            r = parse_requirement(d)
            r.extras = None
            requirements[r.identify()] = r
        for d in conda_dependencies:
            r = parse_requirement(f"conda:{d}")
            if "::" in d:
                assert d.endswith(r.as_line())
            elif "[" not in d:
                assert r.as_line() == re.sub(r"(>=?[\w.]+)\*", r"\g<1>0", d)
            else:
                assert d.startswith(r.as_line())
            assert isinstance(r, CondaRequirement)
            assert not r.extras
            if "::" in d:
                assert r.channel == d.split("::")[0]
            pypi_req = next((v for v in requirements.values() if v.name == r.name), None)
            if pypi_req is not None:
                requirements.pop(pypi_req.identify())
                if not r.specifier:
                    r.specifier = pypi_req.specifier
            requirements[r.identify()] = r
        return requirements

    @pytest.mark.parametrize(**DEPENDENCIES)
    @pytest.mark.parametrize(**GROUPS)
    @pytest.mark.parametrize("as_default_manager", [False, True], ids=["", "as_default_manager"])
    def test_get_dependencies(self, project, dependencies, conda_dependencies, group, as_default_manager):
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
                conf["tool"]["pdm"].setdefault("conda", dict())["as_default_manager"] = True

            return conf

        project.pyproject._data.update(project_conf(dependencies, conda_dependencies, group, as_default_manager))

        if group != "default":
            group = "dev"

        requirements = self._parse_requirements(dependencies, conda_dependencies, as_default_manager)
        project_requirements = project.get_dependencies(group)
        for name, req in project_requirements.items():
            assert req == requirements[name]
            assert isinstance(req, type(requirements[name]))
        assert all("[" not in k for k in project_requirements)

    @pytest.mark.parametrize(**DEPENDENCIES)
    @pytest.mark.parametrize(**GROUPS)
    @pytest.mark.parametrize("python_packages", [True, False])
    def test_add_dependencies(self, project, dependencies, conda_dependencies, group, python_packages):
        requirements = self._parse_requirements(dependencies, conda_dependencies)

        group_name = group if group == "default" else "dev"
        dev = group == "dev"
        project.add_dependencies(requirements, to_group=group_name, dev=dev)
        project_requirements = project.get_dependencies(group_name)
        for name, req in project_requirements.items():
            assert req == requirements[name]
            assert isinstance(req, type(requirements[name]))
        if conda_dependencies and python_packages:
            asserted = 0
            _dependencies, _ = project.get_pyproject_dependencies(group_name, dev)
            _conda_dependencies = project.get_conda_pyproject_dependencies(group_name, dev)
            for d in conda_dependencies:
                d = d.split("[")[0].split("=")[0]
                for r in _dependencies:
                    if d.split("::")[-1] in r:
                        asserted += 1
                        break
                for r in _conda_dependencies:
                    if d in r:
                        asserted += 1
                        break
            assert asserted == len(conda_dependencies) * 2
        assert all("[" not in k for k in project.get_dependencies(group_name))
