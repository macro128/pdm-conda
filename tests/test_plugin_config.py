import pytest
from pdm.exceptions import ProjectError


class TestPluginConfig:
    @pytest.mark.parametrize("channels", [[], ["conda-forge"]])
    @pytest.mark.parametrize("runner", ["micromamba", "mamba", "conda", None])
    def test_get_configs(self, project, channels, runner):
        """
        Test loading configs correctly
        """
        dependencies = ["pytest"]
        optional_dependencies = {"dev": ["pytest"]}
        runner = "micromamba"
        conf = {
            "dependencies": dependencies,
            "optional-dependencies": optional_dependencies,
        }
        if channels:
            conf["channels"] = channels
        else:
            channels = ["defaults"]

        if runner:
            conf["runner"] = runner
        else:
            runner = "conda"
        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": conf,
                    },
                },
            },
        )
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
