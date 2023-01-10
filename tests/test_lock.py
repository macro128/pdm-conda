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
        from pdm_conda.project import CondaProject

        python_requirements = {c["name"] for c in PYTHON_REQUIREMENTS}
        conda_response = [c for c in conda_response if c["name"] not in python_requirements]
        package = conda_response[0]["name"]
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
                    "project": {"dependencies": [conda_response[1]["name"]], "requires-python": ">=3.10"},
                },
            )

        requirements = [r.as_line() for r in project.get_dependencies().values() if isinstance(r, CondaRequirement)] + [
            f"python=={project.python.version}",
        ]
        cmd = ["lock", "-v"]
        if refresh:
            cmd.append("--refresh")
        core.main(cmd, obj=project)

        assert isinstance(project, CondaProject)
        assert package in project.conda_packages

        assert mock_conda.call_count == 3
        cmd_order = ["create", "install", "remove"]

        for (cmd,), kwargs in mock_conda.call_args_list:
            assert cmd[0] == self.conda_runner
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand == "install":
                assert set(kwargs["dependencies"]) == set(requirements)

        assert not cmd_order
        lockfile = project.lockfile
        packages = lockfile["package"]
        assert len(packages) == len([c for c in project.conda_packages if c not in python_requirements])
        for p in packages:
            name = p["name"]
            assert name in project.conda_packages
            p_info = project.conda_packages[name]
            if p_info.requires_python:
                assert p["requires_python"] == p_info.requires_python
            assert p["url"] == p_info.link.url

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("empty_conda_list", [False])
    @pytest.mark.parametrize("group", ["default", "dev", None])
    def test_lock_refresh(self, core, project, mock_conda, conda_response, group):
        self.test_lock(core, project, mock_conda, conda_response, group, False)
        self.test_lock(core, project, mock_conda, conda_response, group, False, refresh=True)
