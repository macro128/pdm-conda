import pytest
from pdm.exceptions import ProjectError


class TestPluginConfig:
    @pytest.mark.parametrize("channels", [[], ["conda-forge"]])
    @pytest.mark.parametrize("runner", ["micromamba", "mamba", "conda", None])
    @pytest.mark.parametrize("as_default_manager", [True, False, None])
    def test_get_configs(self, project, channels, runner, as_default_manager):
        """
        Test loading configs correctly
        """
        dependencies = ["pytest"]
        optional_dependencies = {"dev": ["pytest"]}

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
        if isinstance(as_default_manager, bool):
            conf["as_default_manager"] = as_default_manager
        else:
            as_default_manager = False

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
        assert config.as_default_manager == as_default_manager

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
