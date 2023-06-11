# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.11.0] - 10/06/2023

### Added

* Now compatible with `pdm>=v2.7`.
* Use lazy import to reduce the startup time of the CLI.

### Fixed

* If `conda.as-defualt-manager` is `true` then add requirements to `conda.dependencies` if they aren't python packages
  when using `pdm add` without `--conda` flag.

## [0.10.0] - 22/05/2023

### Added

* Now compatible with `pdm>=v2.6`.

### Fixed

* Lockfile hash includes `pdm-conda` configs.
* When using `-G :all` in `pdm install/lock` consider `pdm-conda` defined groups.
* Ensure all requirements are considered for conda resolution update

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
