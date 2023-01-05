# Changelog

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
