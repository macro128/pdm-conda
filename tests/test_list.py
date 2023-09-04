import pytest


@pytest.mark.usefixtures("fake_python")
class TestList:
    @pytest.mark.parametrize("runner", ["micromamba", "conda"])
    def test_list(self, pdm, project, conda, conda_info, runner, mock_conda_mapping, installed_packages, working_set):
        """
        Test `list` command work as expected
        """

        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": {
                            "runner": runner,
                        },
                    },
                },
            },
        )
        # fake installation
        for p in conda_info:
            if p["name"] not in [ip["name"] for ip in installed_packages]:
                installed_packages.append(p)
        result = pdm(["list"], obj=project, strict=True)

        for p in conda_info:
            assert p["name"] in result.stdout
        for p in installed_packages:
            assert p["name"] in result.stdout
        for (cmd,), _ in conda.call_args_list:
            assert cmd[0] == runner
            assert cmd[1] == "list"

        assert conda.call_count == 1
