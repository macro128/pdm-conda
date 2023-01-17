from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from pdm_conda.mapping import DOWNLOAD_DIR_ENV_VAR


@pytest.fixture
def patch_download_dir(monkeypatch):
    with TemporaryDirectory() as d:
        monkeypatch.setenv(DOWNLOAD_DIR_ENV_VAR, d)
        yield d


class TestMapping:
    @pytest.mark.parametrize("conda_mapping", [{"pytest": "pytest-conda", "other": "other-conda"}, dict()])
    def test_download_mapping(self, patch_download_dir, project, conda_mapping, mocked_responses):
        """
        Test project conda_mapping downloads conda mapping just one and mapping is as expected
        """
        from pdm_conda.mapping import MAPPINGS_URL

        assert project.config["conda.pypi-mapping.download-dir"] == patch_download_dir

        response = ""
        for pypi_name, conda_name in conda_mapping.items():
            response += f"""
            {pypi_name}:
                conda_name: {conda_name}
                import_name: {pypi_name}
                mapping_source: other
                pypi_name: {pypi_name}
            """
        rsp = mocked_responses.get(MAPPINGS_URL, body=response)
        from pdm_conda.mapping import get_pypi_mapping

        for _ in range(5):
            assert get_pypi_mapping() == conda_mapping
        assert rsp.call_count == 1
        for ext in ["yaml", "json"]:
            assert (Path(patch_download_dir) / f"pypi_mapping.{ext}").exists()
        get_pypi_mapping.cache_clear()
