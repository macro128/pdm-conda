from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, cast

from pdm.installers import Synchronizer

from pdm_conda.environments import CondaEnvironment
from pdm_conda.models.candidates import CondaCandidate
from pdm_conda.models.requirements import strip_extras
from pdm_conda.models.setup import CondaSetupDistribution

if TYPE_CHECKING:
    from collections.abc import Collection

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
        use_install_cache: bool | None = None,
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
            use_install_cache,
        )
        self.environment = cast(CondaEnvironment, environment)
        self.parallel = bool(self.parallel)  # type: ignore

    @cached_property
    def candidates(self) -> dict[str, Candidate]:
        candidates = super().candidates
        # if key is requirement with extras, add candidate without extras if it doesn't exist
        for key in list(candidates):
            if (
                isinstance(can := candidates[key], CondaCandidate)
                and candidates.get(name := strip_extras(key)[0], None) is None
            ):
                candidates[name] = can
        return candidates

    def compare_with_working_set(self) -> tuple[list[str], list[str], list[str]]:
        to_add, to_update, to_remove = super().compare_with_working_set()
        if not isinstance(self.environment, CondaEnvironment):
            return to_add, to_update, to_remove

        # deactivate parallel execution if uninstall
        self.parallel = self.environment.project.config["install.parallel"]
        if to_remove:
            to_remove = [p for p in to_remove if p not in self.environment.env_dependencies]

        num_install = 0
        for pkgs in (to_add, to_update):
            num_install += len([p for p in pkgs if isinstance(self.candidates[p], CondaCandidate)])

        num_remove = 0
        for pkgs in (to_remove, to_update):
            num_remove += len([p for p in pkgs if isinstance(self.working_set[p], CondaSetupDistribution)])

        if self.parallel and num_remove > 0:
            if not self.dry_run:
                self.environment.project.core.ui.echo("Deactivating parallel uninstall.")
            self.parallel = False

        batched_commands = self.environment.project.conda_config.batched_commands
        self.manager.prepare_batch_operations(
            num_install=num_install if batched_commands else 0,
            num_remove=num_remove if batched_commands else 0,
        )

        return to_add, to_update, to_remove
