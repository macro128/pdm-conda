import pytest


class TestProject:
    @pytest.mark.parametrize(
        ["dependencies", "conda_dependencies"],
        [
            (["pytest"], ["pytest-cov"]),
            (["pytest>=3.1"], ["pytest"]),
            (["pytest[extra]"], ["pytest"]),
            (["pytest"], ["pytest[extra]"]),
            (["pytest>=3.1"], ["pytest==52"]),
            ([], ["conda-channel::pytest"]),
            (["pytest"], []),
        ],
        ids=[
            "different pkgs",
            "pypi version override",
            "conda extras override",
            "conda no extras",
            "conda version override",
            "conda channel",
            "only pypi",
        ],
    )
    def test_get_dependencies(self, project, dependencies, conda_dependencies):
        """
        Test get project dependencies with conda dependencies and correct parse requirements
        """
        from pdm_conda.models.requirements import CondaRequirement, parse_requirement

        project.pyproject._data.update(
            {
                "project": {"dependencies": dependencies},
                "tool": {
                    "pdm": {
                        "conda": {
                            "dependencies": conda_dependencies,
                        },
                    },
                },
            },
        )
        requirements = dict()
        for d in dependencies:
            r = parse_requirement(d)
            r.extras = None
            requirements[r.identify()] = r
        for d in conda_dependencies:
            r = parse_requirement(d, conda_managed=True)
            if "[" not in d:
                assert r.as_line() == d
            else:
                assert d.startswith(r.as_line())
            assert isinstance(r, CondaRequirement)
            assert not r.extras
            if "::" in d:
                assert r.channel == d.split("::")[0]
            if (
                old_dep := requirements.get(r.identify(), None)
            ) is not None and old_dep.specifier is not None:
                r.specifier = old_dep.specifier
            requirements[r.identify()] = r
        assert project.get_dependencies() == requirements
        assert all("[" not in k for k in project.get_dependencies())
