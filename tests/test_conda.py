import pytest
from pytest_mock import MockFixture


class TestCondaUtils:
    @pytest.mark.parametrize("runner", ["conda", "micromamba", "mamba"])
    def test_conda_not_found(self, runner, mocker: MockFixture):
        mocker.patch("pdm_conda.conda.which", return_value=None)
        from pdm_conda.conda import CondaRunnerNotFoundError, run_conda

        with pytest.raises(CondaRunnerNotFoundError, match=rf"Conda runner {runner} not found"):
            run_conda([runner, "cmd"])
