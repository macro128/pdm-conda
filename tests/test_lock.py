import pytest

from tests.conftest import CONDA_INFO


class TestLock:
    conda_runner = "micromamba"

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("group", ["default", "dev", None])
    def test_lock(self, core, project, mock_conda, conda_response, group, refresh=False):
        """
        Test lock command work as expected
        """
        from pdm_conda.models.requirements import CondaRequirement
        from pdm_conda.project import CondaProject

        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": {
                            "runner": self.conda_runner,
                            "dependencies": ["pdm"],
                        },
                    },
                },
            },
        )
        requirements = [r.as_line() for r in project.get_dependencies().values() if isinstance(r, CondaRequirement)]
        cmd = ["lock", "-v"]
        if refresh:
            cmd.append("--refresh")
        core.main(cmd, obj=project)

        assert isinstance(project, CondaProject)
        assert "pdm" in project.conda_packages

        assert mock_conda.call_count == 3
        cmd_order = ["create", "install", "remove"]

        for (cmd,), kwargs in mock_conda.call_args_list:
            assert cmd[0] == self.conda_runner
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand == "create":
                assert kwargs["dependencies"][0] == f"python=={project.python.version}"
            elif cmd_subcommand == "install":
                assert kwargs["dependencies"] == requirements

        assert not cmd_order
        lockfile = project.lockfile
        packages = lockfile["package"]
        assert len(packages) == len(project.conda_packages)
        for p in packages:
            name = p["name"]
            assert name in project.conda_packages
            p_info = project.conda_packages[name]
            if p_info.requires_python:
                assert p["requires_python"] == p_info.requires_python
            assert p["url"] == p_info.link.url

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("group", ["default", "dev", None])
    def test_lock_refresh(self, core, project, mock_conda, conda_response, group):
        self.test_lock(core, project, mock_conda, conda_response, group)
        self.test_lock(core, project, mock_conda, conda_response, group, refresh=True)
