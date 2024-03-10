import pytest
from pdm.exceptions import ProjectError


@pytest.mark.usefixtures("mock_conda_mapping")
class TestPluginConfig:
    @pytest.mark.parametrize(
        ("config_name", "config_value"),
        [
            ("channels", []),
            ("channels", ["defaults"]),
            ("channels", ["other"]),
            ("excludes", ["another-dep-pip"]),
            ("batched-commands", True),
            ("custom-behavior", True),
            ("batched-commands", False),
            ("dependencies", ["package"]),
            ("dev-dependencies", {"dev": ["package"]}),
            ("optional-dependencies", {"other": ["package"]}),
            ("pypi-mapping.url", "https://example.com/mapping.yaml"),
            ("pypi-mapping", {"url": "https://example.com/mapping.yaml"}),
        ],
    )
    @pytest.mark.parametrize("set_before", [True, False])
    def test_set_configs(self, project, mocker, set_before, config_name, config_value):
        """
        Test settings configs correctly
        """
        from pdm_conda.models.config import _CONFIG_MAP, CONFIGS

        config = project.conda_config
        subscribed = mocker.spy(project.pyproject._data, "update")
        assert_value = config_value

        if set_before:
            project.pyproject._data.update(
                {
                    "tool": {
                        "pdm": {
                            "conda": {config_name: config_value},
                        },
                    },
                },
            )
        conda_config_name = config_name
        if config_name == "pypi-mapping" and isinstance(config_value, dict):
            for k, v in config_value.items():
                conda_config_name = f"{config_name}.{k}"
                assert_value = v
                break
        config_default = next(
            filter(lambda n: n[0] in (f"conda.{conda_config_name}", f"conda.{config_name}"), CONFIGS),
        )[1].default
        conda_config_name = _CONFIG_MAP[conda_config_name]
        if set_before:
            assert getattr(config, conda_config_name) == assert_value

        assert subscribed.call_count == (1 if set_before else 0)
        if config_value is not None:
            with config.write_project_config():
                setattr(config, conda_config_name, assert_value)
            project.pyproject.reload()
            if not set_before and config_value == config_default:
                assert (
                    "conda" not in project.pyproject.settings or config_name not in project.pyproject.settings["conda"]
                )
            else:
                _config = project.pyproject.settings["conda"]
                for k in config_name.split("."):
                    _config = _config[k]

                assert config_value == _config

    @pytest.mark.parametrize(
        ("config_name", "config_value"),
        [
            ("channels", []),
            ("channels", ["defaults"]),
            ("excludes", ["another-dep-pip"]),
            ("batched-commands", True),
            ("batched-commands", False),
            ("dependencies", ["package"]),
        ],
    )
    def test_with_config(self, project, mocker, config_name, config_value):
        config = project.conda_config
        subscribed = mocker.spy(project.pyproject._data, "update")
        conda_config_name = config_name.replace("-", "_")
        old_value = getattr(config, conda_config_name)
        project.pyproject.write(False)
        with config.with_config(**{conda_config_name: config_value}):
            assert not config._set_project_config
            assert getattr(config, conda_config_name) == config_value
        assert getattr(config, conda_config_name) == old_value
        assert subscribed.call_count == 0

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

    @pytest.mark.parametrize("name", ["runner", "installation-method", "runner"])
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
