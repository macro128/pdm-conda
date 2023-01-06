import pytest

from tests.conftest import CONDA_INFO


class TestInstall:
    conda_runner = "micromamba"

    @pytest.mark.parametrize("conda_response", CONDA_INFO)
    @pytest.mark.parametrize("dry_run", [True, False])
    def test_install(self, core, project, mock_conda, conda_response, dry_run):
        """
        Test `install` command work as expected
        """
        from pdm_conda.models.requirements import CondaRequirement

        project.pyproject._data.update(
            {
                "tool": {
                    "pdm": {
                        "conda": {
                            "runner": self.conda_runner,
                            "dependencies": ["dep"],
                        },
                    },
                },
            },
        )
        requirements = [r.as_line() for r in project.get_dependencies().values() if isinstance(r, CondaRequirement)]
        command = ["install", "-v", "--no-self"]
        if dry_run:
            command.append("--dry-run")
        core.main(command, obj=project)
        assert mock_conda.call_count == 3 + (0 if dry_run else len(conda_response))
        cmd_order = ["create", "install", "remove"] + ["install"] * (0 if dry_run else len(conda_response))
        install_dep = False
        for (cmd,), kwargs in mock_conda.call_args_list:
            assert cmd[0] == self.conda_runner
            cmd_subcommand = cmd[1]
            assert cmd_subcommand == cmd_order.pop(0)
            if cmd_subcommand == "create":
                assert kwargs["dependencies"][0] == f"python=={project.python.version}"
            elif cmd_subcommand == "install":
                if not install_dep:
                    assert kwargs["dependencies"] == requirements
                    install_dep = True
                else:
                    deps = kwargs["dependencies"]
                    assert len(deps) == 1

                    def format_url(package):
                        url = package["url"]
                        for h in ["sha256", "md5"]:
                            if h in package:
                                url += f"#{h}={package[h]}"
                        return url

                    assert deps[0] in [format_url(p) for p in conda_response]

        assert not cmd_order
