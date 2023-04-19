# pdm-conda

A PDM plugin to resolve/install/uninstall project dependencies with Conda.

## Configuration

| Config item                       | Description                                                                                          | Default value       | Possible values                | Environment variable        |
|-----------------------------------|------------------------------------------------------------------------------------------------------|---------------------|--------------------------------|-----------------------------|
| `conda.runner`                    | Conda runner executable                                                                              | `conda`             | `conda`, `mamba`, `micromamba` | `CONDA_RUNNER`              |
| `conda.solver`                    | Solver to use for Conda resolution                                                                   | `conda`             | `conda`, `libmamba`            | `CONDA_SOLVER`              |
| `conda.channels`                  | Conda channels to use, order will be enforced                                                        | `[]`                |                                |                             |
| `conda.as-default-manager`        | Use Conda to install all possible requirements                                                       | `False`             |                                | `CONDA_AS_DEFAULT_MANAGER`  |
| `conda.batched-commands`          | Execute batched install and remove Conda commands, when True the command is executed only at the end | `False`             |                                | `CONDA_BATCHED_COMMANDS`    |
| `conda.excludes`                  | Array of dependencies to exclude from Conda resolution                                               | `[]`                |                                |                             |
| `conda.installation-method`       | Installation method to use when installing dependencies with Conda                                   | `hard-link`         | `hard-link`, `copy`            | `CONDA_INSTALLATION_METHOD` |
| `conda.dependencies`              | Array of dependencies to install with Conda, analogue to `project.dependencies`                      | `[]`                |                                |                             |
| `conda.optional-dependencies`     | Groups of optional dependencies to install with Conda, analogue to `project.optional-dependencies`   | `{}`                |                                |                             |
| `conda.dev-dependencies`          | Groups of development dependencies to install with Conda, analogue to `tool.pdm.dev-dependencies`    | `{}`                |                                |                             |
| `conda.pypi-mapping.download-dir` | PyPI-Conda mapping download directory                                                                | `$HOME/.pdm-conda/` |                                | `PYPI_MAPPING_DIR`          |

All configuration items use prefix `pdm.tool`, this is a viable configuration:

```toml
[tool.pdm.conda]
runner = "micromamba"
channels = ["conda-forge/noarch", "conda-forge", "anaconda"]
dependencies = ["pdm"]
as-default-manager = true
solver = "libmamba"
excludes = ["pytest-cov"] # don't install with conda even if it's a dependency from other packages
installation-method = "copy"
batched-commands = true

[tool.pdm.conda.pypi-mapping]
download-dir = "/tmp"

[tool.pdm.conda.optional-dependencies]
extra = ["anaconda:ffmpeg"] # non python dependency, obtained from anaconda channel

[tool.pdm.conda.dev-dependencies]
dev = ["pytest"]
```

## Usage

This plugin adds capabilities to the default PDM commands.

### Working commands

The following commands were tested and work:

* `pdm lock`
* `pdm install`
* `pdm add`:
    * To add a Conda managed package `--conda` flag can be used multiple times followed a package (analogue
      to `--editable`).
    * You can specify per package Conda channel using conda notation `channel::package`.
    * You also can specify a default Conda channel with `-c` or `--channel`.
    * With flag `-r` or `--runner` you can specify the Conda runner to use.
* `pdm remove`
* `pdm list`
* `pdm info`

### How it works

#### Using conda/libmamba solver

PDM invokes Conda solver to resolve conda packages each time a PDM candidate makes a change in the last Conda
resolution.

If only Conda packages are used (i.e. setting `conda.as-default-manager` to `true` and no `conda.excludes`) then Conda
solver is invoked only once.

### Settings overriden

In order to use Conda to install packages some settings were overriden:

* `python.use_venv` if conda settings detected in `pyproject.toml` this setting is set to `True`.
* `python.use_pyenv` if conda settings detected in `pyproject.toml` this setting is set to `False`.
* `venv.backend` if conda settings detected in `pyproject.toml` this setting is set to `conda.runner`.
* `venv.location` if conda settings detected in `pyproject.toml` and `VIRTUAL_ENV` or `CONDA_PREFIX` environment
  variables are set then this setting is set to the value of the environment variable.
* `install.parallel` if some Conda managed packages are to be uninstalled or updated this option is disabled
  momentarily.

## Development

For development `docker-compose` files exist in `deploy` directory, helper script `deploy/docker-compose.sh` can be used
for executing docker.

For running dev environment:

```bash
bash deploy/docker-compose.sh -d up
```

And for productive environment:

```bash
bash deploy/docker-compose.sh up
```
