# Changelog

## [0.9.3] - 26/04/2023

### Added

* PyPi mapping fixes included in the package.
* `CondaSetupDistribution` now has `req` property.

### Changed

* All environment variables now use `PDM_CONDA` prefix to avoid conflicts.
* `CondaEnvironment` `python_dependencies` changed to `env_dependencies` and include runner dependencies.

### Fixed

* Conda commands now use `CondaRunner` values to avoid logging errors.
* When using `conda/mamba` avoid listing PyPi packages as Conda managed.


## [0.9.2] - 21/04/2023

### Fixed

* Fix explicit lockfile generation.

## [0.9.1] - 21/04/2023

### Changed

* `conda install` now uses explicit lockfile to avoid resolution.
* Conda managed packages now save url and hash in `metadata` table of lockfile to match pdm behavior.

### Fixed

* `pdm add` now saves correct custom Conda package version in pyproject.toml.
* Correctly parse Conda candidates when using `conda search` to find them on resolution.

## [0.9.0] - 19/04/2023

### Added

* Config `conda.solver` to use Conda solver to resolve Conda requirements.
* `CondaConfig.with_config` contextmanager to temporarily set a config.
* Use `conda create` to get a resolution.
* Add conda resolution to `CondaRepository`.
* Add conda resolution to `CondaResolver`.

### Changed

* Allow `CondaRequirement` to validate if `Candidate` is compatible.
* Sort `CondaCandidates` instead of packages.
* `Environment.python_requires` now matches installed python to force it in conda resolution.
* `CondaResolver` now uses conda resolution.

### Fixed

* If `conda.as-defualt-manager` is `true` then add requirements to `conda.dependencies` if it has `channel`
  or `build_string`.

## [0.8.1] - 17/04/2023

### Changed

* Use Conda channels priority in package sorting.
* `CondaProject` now contains info from default_channels, virtual_packages and platform.

### Fixed

* Non-conda packages now get installed in the correct directory for python to find them.
* Fix `batched-commands` triggering unexpected behaviour.
* Conda command execution fixes.
* PyPI-Conda mapping always returns name in lower to respect conda naming conventions.

## [0.8.0] - 09/04/2023

### Added

* Config `conda.batched-commands` to use `conda` `install` and `remove` batched commands.
* Show runner commands when using flag `-vv`.
* Show informative logs when using flag `-vv`.

### Changed

* Avoid using Conda for file requirements resolutions and self building.
* Config `conda.excluded` changed to `conda.excludes`.

### Fixed

* `pdm add` doesn't fail when using with a conda specifier.
* `pdm add/remove` doesn't fail when using quited specifiers.
* More Conda specifiers displayed correctly.
* Adding dependencies to pyproject with a conda specifier works correctly.
* `micromamba` and `mamba` now remove only specified dependency.
* `pdm info` shows correct packages location.
* Avoid adding conda dependencies tables to pyproject.toml when not needed.

## [0.7.1] - 04/04/2023

### Changed

* Use `repoquery search` instead of `search` when runner is `mamba` or `micromamba`.

### Fixed

* Parse conda packages version fixes.

## [0.7.0] - 04/04/2023

### Added

* Sort packages
  following [mamba specification](https://mamba.readthedocs.io/en/latest/advanced_usage/package_resolution.html).

### Fixed

* Improved compatibility with `conda` and `mamba` commands.
* Better conda error reports.
* Parse conda packages version fixes.

## [0.6.0] - 29/03/2023

### Added

* New Provider classes to override packages search preference.

### Changed

* Now project `python_requires` matches the installed python version.
* Avoid using `conda lock`.

### Fixed

* Duplicated channels on `pdm add`.
* Virtual packages are parsed as any other requirement.
* `CondaProject.iter_groups` includes conda dependency groups.

## [0.5.3] - 25/01/2023

### Fixed

* Incorrect constrains update on resolution.

## [0.5.2] - 25/01/2023

### Fixed

* Incorrect building fix and use of `pdm-backend` as backend.

## [0.5.0] - 25/01/2023

### Added

* New classes `CondaResolver` and `CondaResolution` to use Conda packages' constrains when resolving dependencies.
* Config `conda.excluded` to exclude requirements from Conda resolution.
* Config `conda.installation-method` to select Conda installation method.
* Environment variables to configs.

### Changed

* If `conda.as-default-manager` is `true`, even dependencies from PyPI packages will be obtained from Conda.
* `install.parallel` only deactivates if Conda packages are set to uninstall/update.
* When parsing OR Conda package specifier (i.e. `>=2,<3`), keep greater version specifier

### Fixed

* Fixes when parsing Conda packages' version.

## [0.4.0] - 17/01/2023

### Added

* Conda-PyPI mapping to avoid conflicts.
* Config `conda.pypi-mapping.download-dir` to manage where mapping is downloaded.
* `save_version_specifiers` and `format_lockfile` monkeypatching

### Changed

* New class `CondEnvironment` instead of monkeypatching.

### Fixed

* `pdm add` provoked conda usage even if not initialized.

## [0.3.1] - 11/01/2023

### Fixed

* Change conda requirement specifier `>=x.*` for `>=x.0` to avoid parse errors.

## [0.3.0] - 11/01/2023

### Added

* Use `conda search` to get candidates.
* Add conda virtual packages support to project.

### Changed

* Merged `CondaCandidate` with `CondaPackage`.
* Better detection of initialized conda configuration.
* Remove `find_matches` monkeypatching.

### Fixed

* Better conda `parse_requirement`.

## [0.2.0] - 10/01/2023

### Added

* `pdm list` support.
* `pdm install` support.
* `pdm add` support.
* `pdm remove` support.
* New class `CondaSynchronizer` to avoid deleting python installation dependencies.
* New class `CondaSetupDistribution` to manage conda package distribution.
* New class `CondaInstallManager` to install/uninstall packages using Conda.
* Config `conda.as_default_manager` to install all posible requirements with Conda.
* `normalize_name` don't overwrite _ in names.

### Changed

* Deactivate parallel uninstall.
* `req` property in `CondaCandidate` only changes if new value's type is `CondaRequirement`.

## [0.1.0] - 05/01/2023

### Added

* Added "channel_url" to conda lock entry.
* Monkeypatch `make_candidate` to return `CondaCandidate` when necessary.

### Fixed

* `pdm lock --refresh` working.

### Changed

* New class `CondaProject` instead of monkeypatching.
* New class `LockedCondaRepository` instead of monkeypatching.
* New class `PyPICondaRepository` instead of monkeypatching.
* `CondaCandidate.prepare` returns `CondaPreparedCandidate` instead of monkeypatching.

## [0.0.1] - 02/01/2023

### Added

* `pdm lock` support, `--refresh` flag not working.
