from typing import Collection

from pdm.installers import Synchronizer
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment

from pdm_conda.plugin import conda_search
from pdm_conda.utils import normalize_name


def _update_dependencies(name, packages, project, dependencies):
    if name in dependencies or name not in packages:
        return
    dependencies.add(name)
    dist = packages[name]
    candidates = conda_search(f"{dist.name}=={dist.version}", project, channel=dist.extras.get("channel", None))
    build_string = dist.extras["build_string"]
    candidate = next(c for c in candidates if c.build_string == build_string)
    for dep in candidate.dependencies:
        normalized_name = normalize_name(dep.name)
        _update_dependencies(normalized_name, packages, project, dependencies)
        dependencies.add(normalized_name)


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
        self.parallel = bool(self.parallel)  # type: ignore

    def compare_with_working_set(self) -> tuple[list[str], list[str], list[str]]:
        to_add, to_update, to_remove = super().compare_with_working_set()

        # get python dependencies and avoid removing them
        python_dependencies: set[str] = set()
        _update_dependencies("python", self.working_set, self.environment.project, python_dependencies)
        to_remove = [p for p in to_remove if p not in python_dependencies]
        # deactivate parallel execution if uninstall
        if to_remove or to_update:
            if self.parallel:
                self.environment.project.core.ui.echo("Deactivating parallel uninstall.")
            self.parallel = False
        else:
            self.parallel = self.environment.project.config["install.parallel"]

        return to_add, to_update, to_remove
