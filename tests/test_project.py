import re
from pathlib import Path
from tempfile import TemporaryDirectory

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
CONDA_MAPPING = dict(
    argnames="conda_mapping",
    argvalues=[{"pytest-conda": "pytest"}],
    ids=["use conda mapping"],
)
GROUPS = dict(argnames="group", argvalues=["default", "dev", "optional"])


class TestProject:
    def _parse_requirements(
        self,
        dependencies,
        conda_dependencies,
        conda_mapping,
        conda_only=None,
        as_default_manager=False,
    ):
        from pdm_conda.models.requirements import CondaRequirement, parse_requirement

        conda_only = conda_only or set()
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
            d = d.strip()
            name = d
            for s in [" ", "=", "!", ">", "<", "~"]:
                name = name.split(s)[0]
            name = name.strip()
            d = conda_mapping.get(name.split("[")[0].split("::")[-1], name) + d[len(name) :]
            r = parse_requirement(f"conda:{d}")
            if name in conda_only:
                r.is_python_package = False
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

    @pytest.mark.parametrize("conda_mapping", [dict(), {"pytest-conda": "pytest", "other-conda": "other"}])
    def test_download_mapping(self, project, conda_mapping, mocked_responses):
        """
        Test project conda_mapping downloads conda mapping just one and mapping is as expected
        """
        with TemporaryDirectory() as d:
            project.pyproject._data.update(
                {
                    "tool": {
                        "pdm": {
                            "conda": {
                                "pypi-mapping": {"download-dir": d},
                            },
                        },
                    },
                },
            )

            from pdm_conda.mapping import MAPPINGS_URL

            response = ""
            for conda_name, pypi_name in conda_mapping.items():
                response += f"""
                {pypi_name}:
                    conda_name: {conda_name}
                    import_name: {pypi_name}
                    mapping_source: other
                    pypi_name: {pypi_name}
                """
            rsp = mocked_responses.get(MAPPINGS_URL, body=response)

            for _ in range(5):
                project.conda_mapping == conda_mapping
            assert rsp.call_count == 1
            for ext in ["yaml", "json"]:
                assert (Path(d) / f"pypi_mapping.{ext}").exists()

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
        conda_mapping,
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
                conf["tool"]["pdm"].setdefault("conda", dict())["as_default_manager"] = True

            return conf

        project.pyproject._data.update(project_conf(dependencies, conda_dependencies, group, as_default_manager))

        if group != "default":
            group = "dev"

        requirements = self._parse_requirements(
            dependencies,
            conda_dependencies,
            conda_mapping,
            as_default_manager=as_default_manager,
        )
        project_requirements = project.get_dependencies(group)
        for name, req in project_requirements.items():
            assert req == requirements[name]
            assert isinstance(req, type(requirements[name]))
        assert all("[" not in k for k in project_requirements)

    @pytest.mark.parametrize(**DEPENDENCIES)
    @pytest.mark.parametrize(**GROUPS)
    @pytest.mark.parametrize(**CONDA_MAPPING)
    @pytest.mark.parametrize("conda_only", [[], ["pytest-cov"]])
    def test_add_dependencies(
        self,
        project,
        dependencies,
        conda_dependencies,
        group,
        conda_mapping,
        mock_conda_mapping,
        conda_only,
    ):
        requirements = self._parse_requirements(dependencies, conda_dependencies, conda_mapping, conda_only)

        group_name = group if group == "default" else "dev"
        dev = group == "dev"
        project.add_dependencies(requirements, to_group=group_name, dev=dev)
        project_requirements = project.get_dependencies(group_name)
        for name, req in project_requirements.items():
            assert req == requirements[name]
            assert isinstance(req, type(requirements[name]))

        if conda_dependencies:
            _dependencies, _ = project.get_pyproject_dependencies(group_name, dev)
            _conda_dependencies = project.get_conda_pyproject_dependencies(group_name, dev)
            for d in conda_dependencies:
                asserted = 0
                d = d.split("[")[0].split("=")[0].split(">")[0].split("::")[-1]
                d = conda_mapping.get(d, d)
                for c in (_dependencies, _conda_dependencies):
                    for r in c:
                        if d in r:
                            asserted += 1
                            break
                assert asserted == len(conda_dependencies) * (2 if requirements[d].is_python_package else 1)
        assert all("[" not in k for k in project.get_dependencies(group_name))
