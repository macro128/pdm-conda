# Changelog

## [0.5.2] - 25/01/2023

### Fixed

- Incorrect building fix and use of `pdm-backend` as backend.

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
