from typing import cast

import pytest


@pytest.mark.usefixtures("fake_python")
@pytest.mark.usefixtures("working_set")
@pytest.mark.parametrize("runner", ["micromamba"])
class TestUpdate:
    default_runner = "micromamba"

    @pytest.mark.parametrize("packages", [["'dep'"], [], ['"dep"', "another-dep"]])
    @pytest.mark.parametrize("group", ["default", "other"])
    @pytest.mark.parametrize("dev", [True, False])
    @pytest.mark.parametrize("save_strategy", ["minimum", "compatible", "exact", None])
    @pytest.mark.parametrize("custom_behavior", [True, False])
    def test_update_custom_behavior(
        self,
        pdm,
        project,
        conda,
        packages,
        runner,
        mock_conda_mapping,
        installed_packages,
        group,
        save_strategy,
        dev,
        custom_behavior,
    ):
        """
        Test `update` command work as expected using custom behavior
        """
        from pdm_conda.project import CondaProject

        project = cast(CondaProject, project)
        conf = project.conda_config
        conf.runner = runner or self.default_runner
        conf.channels = []
        conf.batched_commands = True
        conf.custom_behavior = custom_behavior
        conf.as_default_manager = True
        command = ["add", "--no-self", "--group", group, "-vv"]
        if save_strategy:
            command.append(f"--save-{save_strategy}")
        for package in packages:
            command += ["--conda", package]
        pdm(command, obj=project, strict=True)

        project.pyproject.reload()
        requirements = dict()
        for group in project.iter_groups():
            requirements[group] = project.get_dependencies(group)

        command = ["update", "--no-sync", "-G", ":all"]
        if save_strategy:
            command.append(f"--save-{save_strategy}")
        assert conf.custom_behavior == custom_behavior
        pdm(command, obj=project, strict=True)

        project.pyproject.reload()
        updated_requirements = dict()
        for group in project.iter_groups():
            updated_requirements[group] = project.get_dependencies(group)

        if not custom_behavior:
            assert requirements == updated_requirements
        else:
            candidates = project.locked_repository.all_candidates
            for group, reqs in requirements.items():
                updated = updated_requirements[group]
                for identifier, req in reqs.items():
                    if not req.is_named:
                        assert req == updated[identifier]
                    else:
                        updated_specifier = updated[identifier].specifier
                        assert all(s.version in req.specifier for s in updated_specifier)
                        if save_strategy == "exact":
                            assert all(s.operator == "==" for s in updated_specifier)
                        elif save_strategy == "minimum":
                            assert all(s.operator == ">=" for s in updated_specifier)
                        if save_strategy == "compatible":
                            assert all(s.operator == "~=" for s in updated_specifier)
                            version = candidates[identifier].version
                            assert version in updated_specifier
                            version = version.split(".")[:-1]
                            version[-1] = str(int(version[-1]) + 1)
                            assert ".".join(version) not in updated_specifier
