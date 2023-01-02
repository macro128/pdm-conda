import pytest
from pdm.exceptions import ProjectError


class TestPluginConfig:
    @pytest.mark.parametrize("channels", [[], ["conda-forge"]])
    def test_get_configs(self, project, channels):
        """
        Test loading configs correctly
        """
        dependencies = ["pytest"]
        optional_dependencies = {"dev": ["pytest"]}
        runner = "micromamba"
        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": {
                            "channels": channels,
                            "runner": runner,
                            "dependencies": dependencies,
                            "optional-dependencies": optional_dependencies,
                        },
                    },
                },
            },
        )
        if not channels:
            channels = ["defaults"]

        from pdm_conda.models.config import PluginConfig

        config = PluginConfig.load_config(project)
        assert config.dependencies == dependencies
        assert config.optional_dependencies == optional_dependencies
        assert config.runner == runner
        assert config.channels == channels

    def test_incorrect_runner(self, project):
        """
        Test load config raises on incorrect runner
        """
        runner = "another runner"
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

        from pdm_conda.models.config import PluginConfig

        with pytest.raises(ProjectError, match=f"Invalid Conda runner: {runner}"):
            PluginConfig.load_config(project)
