from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from pdm_conda.mapping import MAPPING_DOWNLOAD_DIR_ENV_VAR


@pytest.fixture
def patch_download_dir(monkeypatch):
    with TemporaryDirectory() as d:
        monkeypatch.setenv(MAPPING_DOWNLOAD_DIR_ENV_VAR, d)
        yield d


@pytest.fixture
def patch_conda_mapping_fixes(mocker, conda_mapping_fixes):
    yield mocker.patch("pdm_conda.mapping.get_mapping_fixes", return_value=conda_mapping_fixes)


class TestMapping:
    @pytest.mark.parametrize("conda_mapping", [{"pytest": "pytest-conda", "other": "other-conda"}, dict()])
    @pytest.mark.parametrize("mapping_url", [None, "https://example.com/mapping.yaml"])
    @pytest.mark.parametrize(
        "conda_mapping_fixes",
        [{"corrected-mapping": "corrected"}, {"pytest": "pytest-corrected"}],
    )
    def test_download_mapping(
        self,
        patch_download_dir,
        project,
        conda_mapping,
        patch_conda_mapping_fixes,
        conda_mapping_fixes,
        mocked_responses,
        mapping_url,
        monkeypatch,
    ):
        """
        Test project conda_mapping downloads conda mapping just one and mapping is as expected
        """
        from pdm_conda.mapping import (
            MAPPING_URL,
            MAPPING_URL_ENV_VAR,
            get_conda_mapping,
            get_pypi_mapping,
        )

        get_pypi_mapping.cache_clear()
        get_conda_mapping.cache_clear()
        if mapping_url is None:
            mapping_url = MAPPING_URL
        monkeypatch.setenv(MAPPING_URL_ENV_VAR, mapping_url)

        assert project.config["conda.pypi-mapping.download-dir"] == patch_download_dir
        assert project.config["conda.pypi-mapping.url"] == mapping_url

        response = ""
        for pypi_name, conda_name in conda_mapping.items():
            response += f"""
            {pypi_name}:
                conda_name: {conda_name}
                import_name: {pypi_name}
                mapping_source: other
                pypi_name: {pypi_name}
            """
        rsp = mocked_responses.get(mapping_url, body=response)

        corrected_mapping = dict(conda_mapping)
        corrected_mapping.update(conda_mapping_fixes)
        for _ in range(5):
            assert get_pypi_mapping() == corrected_mapping
            assert get_conda_mapping() == {k: v for v, k in corrected_mapping.items()}
        assert rsp.call_count == 1
        assert patch_conda_mapping_fixes.call_count == 1
        for ext in ["yaml", "json"]:
            assert (Path(patch_download_dir) / f"pypi_mapping.{ext}").exists()

    @pytest.mark.parametrize("conda_mapping", [{"pytest": "pytest-conda", "other": "other-conda"}])
    @pytest.mark.parametrize("package", ["pytest", "other", "otherPackage"])
    @pytest.mark.parametrize("conda_mapping_fixes", [dict()])
    def test_pypi_mapping(
        self,
        patch_download_dir,
        project,
        conda_mapping,
        patch_conda_mapping_fixes,
        conda_mapping_fixes,
        package,
        mocked_responses,
        monkeypatch,
    ):
        self.test_download_mapping(
            patch_download_dir,
            project,
            conda_mapping,
            patch_conda_mapping_fixes,
            conda_mapping_fixes,
            mocked_responses,
            None,
            monkeypatch,
        )
        from pdm_conda.mapping import pypi_to_conda

        assert pypi_to_conda(package) == conda_mapping.get(package, package.lower())
