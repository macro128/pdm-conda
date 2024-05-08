# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.17.5] - 08/05/2024

### Changed

* Allow selecting a Conda environment on `pdm use` even if base environment is active.
* Force Conda to always fetch all packages info con `conda create --dry-run`.

### Fixed

* Don't show duplicated Conda interpreters on `pdm use`.
* Don't show base Conda env on `pdm env list` or `pdm use`.
* Write plugin related changes on `pdm venv create --with`.
* Fix paths when using on Windows.
* Fix Conda environments not showing on Windows.

## [0.17.4] - 29/04/2024

### Fixed

* Fix big introduced in last version.


## [0.17.3] - 29/04/2024

### Fixed

* Fix locked packages missing groups when Conda resolution has cyclic dependencies.
* Ensure `conda.excludes` is always sorted when saving to `pyproject.toml`

## [0.17.2] - 27/04/2024

### Added

* Now compatible with `pdm==v2.15.1`.

### Fixed

* Fix locked packages missing groups when conflict with Conda constraints.

## [0.17.1] - 22/04/2024

### Fixed

* Fix `pdm lock --refresh` failing with packages with extras.


## [0.17.0] - 22/04/2024

### Added

* Add `conda.auto-exludes` config and auto-excludes behavior.
* Now compatible with `pdm==v2.15.0`.

### Changed

* Allow multiple channels specified using `pdm init --channel`.
* Faster resolution time with mixed Conda and PyPi packages.

### Fixed

* Fix locked packages dropping information when running `pdm lock --refresh`.
* Fix calling `conda` commands unnecessarily on `pdm add/remove/update reuse` when lockfile exists.
* Ensure all commands apply to the correct environment when using Conda.

## [0.16.5] - 18/03/2024

### Fixed

* Fixed pdm not detecting Conda packages.
* Fixed `pdm list --tree --resolve` command not working with Conda packages.

## [0.16.4] - 08/03/2024

### Changed

* Now fails faster if Conda can't find a candidate and shows the error with verbose, suggesting possible Pypi only packages.

## [0.16.3] - 28/02/2024

### Added

* Now compatible with `pdm==v2.12.4`.

### Fixed

* Fix adding resolution rounds when adding Conda packages.
* Conda packages specifiers are always sorted when printed.

## [0.16.2] - 19/02/2024

### Fixed

* Avoid invoking `conda` commands every time a dependency with extras is added.
* Reduce repeated requirements passed to `conda create`.

## [0.16.1] - 18/02/2024

### Fixed

* Correctly parse lockfile with extras.

## [0.16.0] - 04/02/2024

### Added

* Now compatible with `pdm==v2.12.3`.

### Fixed

* Conda packages support extras and markers correctly (even if they are not used by Conda).

## [0.15.0] - 15/12/2023

### Added

* Now compatible with `pdm==v2.11.1`.

### Fixed

* Fix base candidate not appearing when used with extras.
* Fix error installing self.
* Force CondaCandidates for requirement with extras to depend on base candidate.
* If update to CondaCandidate then force Conda usage to remove and install.
* Fix Conda packages sometimes being recognized with a different version.

## [0.14.3] - 21/11/2023

### Changed

* Now compatible with `pdm==v2.10.3`.

### Fixed

* Stop trying to recognize the project name as a Conda package name.
* Don't write configs with default values to `pyproject.toml`.

## [0.14.2] - 11/11/2023

### Changed

* Now compatible with `pdm==v2.10.1` and `python>=3.10,<3.13`.

### Fixed

* `pdm lock --check` don't return error if Conda configuration is not found.

## [0.14.1] - 30/10/2023

### Changed

* Raise `NoConfigError` when specifies incorrect Conda related configs.
* Add `conda.custom-behavior` config.

### Fixed

* Add PyPi mapping fixes.
* Ensure `pdm.conda` arrays can be saved as multiline array.
* Fix Conda dependencies not being treated correctly when using `--conda` option with `conda.as-default-manager` set to
  `false`.
* Fix lockfile formatting when `conda.as-default-manager` set to `false` and Conda dependencies are present.

## [0.14.0] - 29/10/2023

### Added

* Now compatible with `pdm>=v2.10.0`.

### Changed

* Use lock strategies instead of flags.

## [0.13.0] - 11/09/2023

### Added

* `pdm add -ce` or `--conda-excludes` add PyPi packages to the excluded from Conda resolution.
* `pdm add --conda-as-default-manager` sets Conda as default manager.

### Fixed

* Conda channels are correctly saved when added using `pdm add -c` command and Conda configuration was not initialized
  before.
* Don't include dev groups when invoking `pdm lock -G :all --prod`.
* Ensure `cross_platform` is always false when using Conda.

## [0.12.2] - 10/09/2023

### Fixed

* Ensure excluded packaged defined with extras in base requirements are correctly treated on resolution.

## [0.12.1] - 07/09/2023

### Fixed

* Exclude packages defined with extras if base requirement in `conda.excludes`.

## [0.12.0] - 03/09/2023

### Added

* Now compatible with `pdm>=v2.9.1`.
* `pdm init` now shows Conda managed interpreters if runner specifier.
* `pdm venv` commands work with Conda managed environments.
* Now PyPI-Conda mapping url can be set with `conda.pypi-mapping.url` config.

### Changed

* `pdm lock --no-cross-platform` is forced.

### Fixed

* Resolver now respects resolution overrides.
* Only static URLs of the conda packages are stored in the lockfile.

## [0.11.0] - 10/06/2023

### Added

* Now compatible with `pdm>=v2.7`.
* Use lazy import to reduce the startup time of the CLI.

### Fixed

* If `conda.as-default-manager` is `true` then add requirements to `conda.dependencies` if they aren't python packages
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
