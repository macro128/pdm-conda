import pytest

CONDA_INFO = [
    {
        "name": "pdm",
        "depends": [],
        "version": "1.0.0",
        "url": "https://channel.com/package",
        "channel": "https://channel.com",
        "sha256": "this-is-a-hash",
    },
]


@pytest.fixture
def mock_conda(mocker, conda_response: dict):
    install_response = {
        "actions": {
            "LINK": [conda_response],
        },
    }

    def _mock(cmd, **kwargs):
        if cmd[1] == "install":
            return install_response
        else:
            return {"message": "ok"}

    yield mocker.patch("pdm_conda.plugin.run_conda", side_effect=_mock)


class TestLock:
    conda_runner = "micromamba"

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    def test_lock(self, core, project, mock_conda):
        """
        Test lock command work as expected
        """
        from pdm_conda.models.requirements import CondaRequirement

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
        requirements = [
            r.as_line()
            for r in project.get_dependencies().values()
            if isinstance(r, CondaRequirement)
        ]

        core.main(["lock"], obj=project)
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
        lock = project.lockfile

        assert lock

    # @pytest.mark.parametrize("conda_response", CONDA_INFO)
    # def test_lock_refresh(self, core, project, mock_conda):
    #     self.test_lock(core, project, mock_conda)
    #
    #     core.main(["lock", "--refresh"], obj=project)
