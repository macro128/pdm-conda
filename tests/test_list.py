import pytest

from tests.conftest import CONDA_INFO, CONDA_MAPPING


@pytest.mark.parametrize("empty_conda_list", [False])
class TestList:
    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
    @pytest.mark.parametrize("runner", ["micromamba"])
    def test_list(self, pdm, project, conda, conda_response, runner, mock_conda_mapping):
        """
        Test `list` command work as expected
        """

        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": {
                            "runner": runner,
                            "dependencies": ["dep-pip"],
                        },
                    },
                },
            },
        )
        result = pdm(["list"], obj=project)
        assert result.exception is None

        for p in conda_response:
            assert p["name"] in result.stdout
        for (cmd,), _ in conda.call_args_list:
            assert cmd[0] == runner
            assert cmd[1] == "list"

        assert conda.call_count == 1
