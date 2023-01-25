import pytest
from pdm.exceptions import ProjectError


class TestPluginConfig:
    def test_set_configs(self, project, mocker):
        """
        Test settings configs correctly
        """

        config_name = "channels"
        config = project.conda_config
        subscribed = mocker.spy(project.pyproject._data, "update")
        values = [[], ["defaults"], ["other"], None]
        for v in values:
            assert_v = v or []
            project.pyproject._data.update(
                {
                    "tool": {
                        "pdm": {
                            "conda": {config_name: v},
                        }
                        if v is not None
                        else dict(),
                    },
                },
            )
            assert getattr(config, config_name) == assert_v

        assert subscribed.call_count == len(values)
        for v in values[:-1]:
            setattr(config, config_name, v)
            assert v == project.pyproject.settings["conda"][config_name]

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

        if runner:
            conf["runner"] = runner
        else:
            runner = "conda"
        if isinstance(as_default_manager, bool):
            conf["as-default-manager"] = as_default_manager
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
        config = project.conda_config
        assert config.dependencies == dependencies
        assert config.optional_dependencies == optional_dependencies
        assert config.runner == runner
        assert config.channels == channels
        assert config.as_default_manager == as_default_manager

    @pytest.mark.parametrize("name", ["runner", "installation-method"])
    def test_incorrect_config(self, project, name):
        """
        Test load config raises on incorrect config
        """
        config_value = "incorrect config value"
        with pytest.raises(ProjectError, match=f"Invalid Conda [^:]+: {config_value}"):
            project.pyproject._data.update(
                {
                    "tool": {
                        "pdm": {
                            "conda": {
                                name: config_value,
                            },
                        },
                    },
                },
            )
