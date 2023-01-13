from contextlib import redirect_stdout
from io import StringIO

import pytest

from tests.conftest import CONDA_INFO, CONDA_MAPPING


class TestList:
    conda_runner = "micromamba"

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("empty_conda_list", [False])
    @pytest.mark.parametrize("conda_mapping", CONDA_MAPPING)
    def test_list(self, core, project, mock_conda, conda_response, mock_conda_mapping):
        """
        Test `list` command work as expected
        """

        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": {
                            "runner": self.conda_runner,
                            "dependencies": ["dep-pip"],
                        },
                    },
                },
            },
        )
        command = ["list"]
        with StringIO() as output:
            with redirect_stdout(output):
                core.main(command, obj=project)

            o = output.getvalue()
            for p in conda_response:
                assert p["name"] in o

        assert mock_conda.call_count == 1
