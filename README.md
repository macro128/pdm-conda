# pdm-conda

A PDM plugin to install project dependencies with Conda.

## Configuration

| Config item                   | Description                                                                                        | Default value | Possible values                |
|-------------------------------|----------------------------------------------------------------------------------------------------|---------------|--------------------------------|
| `conda.runner`                | Conda runner executable                                                                            | `conda`       | `conda`, `mamba`, `micromamba` |
| `conda.channels`              | Conda channels to use, order will be enforced                                                      | `[defaults]`  |                                |
| `conda.as_default_manager`    | Use Conda to install all possible requirements                                                     | `False`       |                                |
| `conda.dependencies`          | Array of dependencies to install with Conda, analogue to `project.dependencies`                    | `[]`          |                                |
| `conda.optional-dependencies` | Groups of optional dependencies to install with Conda, analogue to `project.optional-dependencies` | `[]`          |                                |
| `conda.dev-dependencies`      | Groups of development dependencies to install with Conda, analogue to `tool.pdm.dev-dependencies`  | `[]`          |                                |

All configuration items use prefix `pdm.tool`, this is a viable configuration:

```toml
[tool.pdm.conda]
runner = "micromamba"
channels = ["conda-forge/noarch", "conda-forge", "anaconda"]
dependencies = ["pdm"]
as_default_manager = true

[tool.pdm.conda.optional-dependencies]
extra = ["anaconda:ffmpeg"] # non python dependency, obtained from anaconda channel

[tool.pdm.conda.dev-dependencies]
dev = ["pytest"]
```

## Usage

This plugin modifies PDM commands so after adding configuration to the pyproject file it's done.

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
