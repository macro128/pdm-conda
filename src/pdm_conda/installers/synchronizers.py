from typing import Collection, cast

from pdm.installers import Synchronizer
from pdm.models.candidates import Candidate

from pdm_conda.models.environment import CondaEnvironment, Environment
from pdm_conda.models.setup import CondaSetupDistribution


class CondaSynchronizer(Synchronizer):
    def __init__(
        self,
        candidates: dict[str, Candidate],
        environment: Environment,
        clean: bool = False,
        dry_run: bool = False,
        retry_times: int = 1,
        install_self: bool = False,
        no_editable: bool | Collection[str] = False,
        use_install_cache: bool = False,
        reinstall: bool = False,
        only_keep: bool = False,
    ) -> None:
        super().__init__(
            candidates,
            environment,
            clean,
            dry_run,
            retry_times,
            install_self,
            no_editable,
            use_install_cache,
            reinstall,
            only_keep,
        )
        self.environment = cast(CondaEnvironment, environment)
        self.parallel = bool(self.parallel)  # type: ignore

    def compare_with_working_set(self) -> tuple[list[str], list[str], list[str]]:
        to_add, to_update, to_remove = super().compare_with_working_set()

        # deactivate parallel execution if uninstall
        self.parallel = self.environment.project.config["install.parallel"]
        if to_remove or to_update:
            if to_remove:
                to_remove = [p for p in to_remove if p not in self.environment.python_dependencies]

            if self.parallel and any(True for d in to_remove + to_update if isinstance(d, CondaSetupDistribution)):
                self.environment.project.core.ui.echo("Deactivating parallel uninstall.")
                self.parallel = False

        return to_add, to_update, to_remove
