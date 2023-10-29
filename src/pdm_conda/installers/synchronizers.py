from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pdm.installers import Synchronizer

from pdm_conda.environments import CondaEnvironment
from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.setup import CondaSetupDistribution

if TYPE_CHECKING:
    from typing import Collection

    from pdm_conda.environments import BaseEnvironment
    from pdm_conda.models.candidates import Candidate


class CondaSynchronizer(Synchronizer):
    def __init__(
        self,
        candidates: dict[str, Candidate],
        environment: BaseEnvironment,
        clean: bool = False,
        dry_run: bool = False,
        retry_times: int = 1,
        install_self: bool = False,
        no_editable: bool | Collection[str] = False,
        reinstall: bool = False,
        only_keep: bool = False,
        fail_fast: bool = False,
    ) -> None:
        super().__init__(
            candidates,
            environment,
            clean,
            dry_run,
            retry_times,
            install_self,
            no_editable,
            reinstall,
            only_keep,
            fail_fast,
        )
        self.environment = cast(CondaEnvironment, environment)
        self.parallel = bool(self.parallel)  # type: ignore

    def compare_with_working_set(self) -> tuple[list[str], list[str], list[str]]:
        to_add, to_update, to_remove = super().compare_with_working_set()

        # deactivate parallel execution if uninstall
        self.parallel = self.environment.project.config["install.parallel"]
        if to_remove:
            to_remove = [p for p in to_remove if p not in self.environment.env_dependencies]

        num_update, num_remove = (
            len([p for p in pks if isinstance(self.working_set[p], CondaSetupDistribution)])
            for pks in (to_update, to_remove)
        )
        if self.parallel and (num_update + num_remove > 0):
            if not self.dry_run:
                self.environment.project.core.ui.echo("Deactivating parallel uninstall.")
            self.parallel = False

        if self.environment.project.conda_config.batched_commands:
            num_adds = len([p for p in to_add if isinstance(self.candidates[p], CondaCandidate)])

            self.manager.prepare_batch_operations(
                num_install=num_adds + num_update,
                num_remove=num_remove + num_update,
            )

        return to_add, to_update, to_remove
