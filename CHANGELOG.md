# Changelog

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

* New class `CondaProject` class instead of monkeypatching.
* New class `LockedCondaRepository` instead of monkeypatching.
* New class `PyPICondaRepository` instead of monkeypatching.
* `CondaCandidate.prepare` returns `CondaPreparedCandidate` instead of monkeypatching.

## [0.0.1] - 02/01/2023

### Added

* `pdm lock` support, `--refresh` flag not working.
