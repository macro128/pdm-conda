import re

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
        ([], ["conda-channel/arch1::pytest-conda"]),
        (["pytest"], []),
        ([], ["pytest-conda>=1.*"]),
        ([], ["pytest-conda>1.*"]),
        ([], ["pytest-conda~=1.0.0"]),
        ([], ["pytest-conda~=1.*"]),
        ([], ["pytest-conda=1"]),
        ([], ["pytest-conda==1.0=build_string"]),
    ],
    ids=[
        "different pkgs",
        "pypi version override",
        "conda extras override",
        "conda no extras",
        "conda version override",
        "conda channel",
        "conda channel with platform",
        "only pypi",
        "star >= specifier",
        "star > specifier",
        "~= specifier",
        "~= star specifier",
        "= specifier",
        "conda with build string",
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
            elif re.search(r"\w=\d", d):
                assert r.as_line() == d.replace("=", "==") + ".*"
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

        for project_requirements in (project.get_dependencies(group), project.all_dependencies[group]):
            for name, req in project_requirements.items():
                conda_req = requirements[req.conda_name]
                assert conda_req == req
                assert isinstance(req, type(conda_req))
                if "~=" in str(req.specifier):
                    line = conda_req.as_line(conda_compatible=True)
                    assert re.match(r".+=[\w.*]+,>=[\w.]+.*", line)
            assert all("[" not in k for k in project_requirements)

    @pytest.mark.parametrize(**DEPENDENCIES)
    @pytest.mark.parametrize(**GROUPS)
    @pytest.mark.parametrize(**CONDA_MAPPING)
    @pytest.mark.parametrize("as_default_manager", [False, True], ids=["", "as_default_manager"])
    def test_add_dependencies(
        self,
        project,
        dependencies,
        conda_dependencies,
        group,
        mock_conda_mapping,
        as_default_manager,
        test_id,
    ):
        from pdm_conda.mapping import conda_to_pypi
        from pdm_conda.models.requirements import CondaRequirement

        project.conda_config.as_default_manager = as_default_manager
        requirements = self._parse_requirements(dependencies, conda_dependencies, as_default_manager=as_default_manager)
        group_name = group if group == "default" else "dev"
        dev = group == "dev"
        project.add_dependencies(requirements, to_group=group_name, dev=dev)
        project_requirements = project.get_dependencies(group_name)
        for name, req in requirements.items():
            assert req == project_requirements[name]
            if isinstance(req, CondaRequirement) and req.is_python_package:
                named_req = req.as_named_requirement()
                if named_req.name != req.name:
                    assert named_req not in project_requirements

        if conda_dependencies:
            _dependencies, _ = project.get_pyproject_dependencies(group_name, dev)
            _conda_dependencies = project.get_conda_pyproject_dependencies(group_name, dev)
            for d in conda_dependencies:
                asserted = 0
                d = d.split("[")[0].split("=")[0].split(">")[0].split("~")[0].split("::")[-1]
                for c in (_conda_dependencies, _dependencies):
                    for r in c:
                        if d in r or conda_to_pypi(d) in r:
                            asserted += 1
                            break
                req = requirements[d]
                num_assertions = 1
                if as_default_manager:
                    if not req.is_python_package or req.channel or req.build_string:
                        num_assertions = 2
                elif req.is_python_package:
                    num_assertions = 2
                assert asserted == len(conda_dependencies) * num_assertions
        assert all("[" not in k for k in project.get_dependencies(group_name))

    @pytest.mark.parametrize(
        ("config_name", "config_value", "must_be_different"),
        [
            ("channels", ["other"], True),
            ("batched_commands", True, False),
            ("runner", "micromamba", False),
            ("solver", "libmamba", False),
            ("installation_method", "copy", False),
            ("as_default_manager", True, True),
            ("dependencies", ["package"], True),
            ("excludes", ["package"], True),
            ("dev_dependencies", {"dev": ["package"]}, True),
            ("optional_dependencies", {"other": ["package"]}, True),
        ],
    )
    def test_pyproject_hash(self, project, config_name, config_value, must_be_different):
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
