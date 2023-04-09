# pdm-conda

A PDM plugin to install project dependencies with Conda.

## Configuration

| Config item                       | Description                                                                                          | Default value       | Possible values                | Environment variable        |
|-----------------------------------|------------------------------------------------------------------------------------------------------|---------------------|--------------------------------|-----------------------------|
| `conda.runner`                    | Conda runner executable                                                                              | `conda`             | `conda`, `mamba`, `micromamba` | `CONDA_RUNNER`              |
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

When PDM detects a Conda managed package, it gets candidates with Conda and then tries to resolve the environment as
with any other requirement.

To keep the resolution consistent with Conda, PDM follows resolution rules from Conda as good as possible.

### Settings overriden

In order to use Conda to install packages some settings were overriden:

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
