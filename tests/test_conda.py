from pathlib import Path

import pytest
from pytest_mock import MockFixture


class TestCondaUtils:
    @pytest.mark.parametrize("runner", ["conda", "micromamba", "mamba"])
    def test_conda_not_found(self, runner, mocker: MockFixture):
        mocker.patch("pdm_conda.conda.which", return_value=None)
        from pdm_conda.conda import CondaRunnerNotFoundError, run_conda

        with pytest.raises(CondaRunnerNotFoundError, match=rf"Conda runner {runner} not found"):
            run_conda([runner, "cmd"])

    @pytest.mark.parametrize(
        "path,expected_path",
        [
            ["<$env:$HOME>/", Path().home()],
            ["~", Path().home()],
            ["<env:$HOME>/", Path().home()],
            ["$HOME", Path().home()],
            ["<$HOME>", Path().home()],
        ],
    )
    def test_fix_path(self, path, expected_path):
        from pdm_conda.utils import fix_path

        assert fix_path(path) == Path(expected_path)
