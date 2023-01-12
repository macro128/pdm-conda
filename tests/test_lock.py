import pytest

from tests.conftest import CONDA_INFO, PYTHON_REQUIREMENTS


class TestLock:
    conda_runner = "micromamba"

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("empty_conda_list", [False])
    @pytest.mark.parametrize("group", ["default", "dev", None])
    @pytest.mark.parametrize("add_conflict", [True, False])
    def test_lock(self, core, project, mock_conda, conda_response, group, add_conflict, refresh=False):
        """
        Test lock command work as expected
        """
        from pdm_conda.models.requirements import CondaRequirement

        python_requirements = {c["name"] for c in PYTHON_REQUIREMENTS}
        conda_response = [c for c in conda_response if c["name"] not in python_requirements]
        package = conda_response[1]["name"]
        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": {
                            "runner": self.conda_runner,
                            "dependencies": [package],
                        },
                    },
                },
            },
        )
        if add_conflict:
            project.pyproject._data.update(
                {
                    "project": {"dependencies": [conda_response[0]["name"]], "requires-python": ">=3.10"},
                },
            )

        requirements = [r.as_line() for r in project.get_dependencies().values() if isinstance(r, CondaRequirement)]
        cmd = ["lock", "-v"]
        if refresh:
            cmd.append("--refresh")
        core.main(cmd, obj=project)

        cmd_order = []
        packages_to_search = set(requirements)
        # not all packages conda managed so run pre_lock
        if add_conflict:
            cmd_order = ["create", "install", "remove"]
            packages_to_search.add(conda_response[0]["name"])
        cmd_order.append("info")
        for c in conda_response:
            for d in c["depends"]:
                packages_to_search.add(d.replace(" ", ""))
        cmd_order.extend(["search"] * len(packages_to_search))

        assert mock_conda.call_count == len(cmd_order)

        requirements.append(f"python=={project.python.version}")
        for (cmd,), kwargs in mock_conda.call_args_list:
            assert cmd[0] == self.conda_runner
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand == "install":
                assert set(kwargs["dependencies"]) == set(requirements)
            elif cmd_subcommand == "search":
                name = next(filter(lambda x: not x.startswith("-"), cmd[2:]))
                assert name in packages_to_search

        packages_to_search = {p.split("=")[0] for p in packages_to_search}
        assert not cmd_order
        lockfile = project.lockfile
        packages = lockfile["package"]
        for p in packages:
            name = p["name"]
            assert name in packages_to_search

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("empty_conda_list", [False])
    @pytest.mark.parametrize("group", ["default", "dev", None])
    def test_lock_refresh(self, core, project, mock_conda, conda_response, group):
        self.test_lock(core, project, mock_conda, conda_response, group, False)
        self.test_lock(core, project, mock_conda, conda_response, group, False, refresh=True)
