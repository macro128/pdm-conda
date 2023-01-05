# pdm-conda

A PDM plugin to install project dependencies with Conda.

## Configuration

| Config item             | Description                                                                                        | Default value | Possible values                |
|-------------------------|----------------------------------------------------------------------------------------------------|---------------|--------------------------------|
| `conda.runner`          | Conda runner executable                                                                            | `conda`       | `conda`, `mamba`, `micromamba` |
| `conda.channels`        | Conda channels to use, order will be enforced                                                      | `[defaults]`  |                                |
| `conda.dependencies`    | Array of dependencies to install with Conda, analogue to `project.dependencies`                    | `[]`          |                                |
| `optional-dependencies` | Groups of optional dependencies to install with Conda, analogue to `project.optional-dependencies` | `[]`          |                                |
| `dev-dependencies`      | Groups of development dependencies to install with Conda, analogue to `tool.pdm.dev-dependencies`  | `[]`          |                                |

All configuration items use prefix `pdm.tool`, this is a viable configuration:

```toml
[tool.pdm.conda]
runner = "micromamba"
channels = ["conda-forge/noarch", "conda-forge", "anaconda"]
dependencies = ["pdm"]

[tool.pdm.conda.optional-dependencies]
extra = ["anaconda:ffmpeg"] # non python dependency, obtained from anaconda channel

[tool.pdm.conda.dev-dependencies]
dev = ["pytest"]
```

## Usage

This plugin modifies PDM commands so after adding configuration to the pyproject file it's done.

## Working commands

The following commands were tested and work:

* `pdm lock`
