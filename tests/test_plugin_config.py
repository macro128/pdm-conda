import pytest
from pdm.exceptions import ProjectError


class TestPluginConfig:
    @pytest.mark.parametrize(
        ("config_name", "config_value"),
        [
            ("channels", []),
            ("channels", ["defaults"]),
            ("channels", ["other"]),
            ("channels", None),
            ("batched-commands", True),
            ("batched-commands", False),
            ("dependencies", ["package"]),
            ("dev-dependencies", {"dev": ["package"]}),
            ("optional-dependencies", {"other": ["package"]}),
        ],
    )
    def test_set_configs(self, project, mocker, config_name, config_value):
        """
        Test settings configs correctly
        """

        config = project.conda_config
        subscribed = mocker.spy(project.pyproject._data, "update")
        if config_value is None:
            assert_value = []
        else:
            assert_value = config_value
        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": {config_name: config_value},
                    }
                    if config_value is not None
                    else dict(),
                },
            },
        )
        conda_config_name = config_name.replace("-", "_")
        assert getattr(config, conda_config_name) == assert_value

        assert subscribed.call_count == 1
        if config_value is not None:
            setattr(config, conda_config_name, config_value)
            project.pyproject.write(False)
            assert config_value == project.pyproject.settings["conda"][config_name]

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
