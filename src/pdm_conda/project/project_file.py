import hashlib
import json

from pdm.project.project_file import PyProject as PyProjectBase


class PyProject(PyProjectBase):
    def content_hash(self, algo: str = "sha256") -> str:
        """
        Generate a hash of the sensible content of the pyproject.toml file.
        When the hash changes, it means the project needs to be relocked.
        :param algo: hash algorithm name
        :return: pyproject.toml hash
        """
        pdm_conda_data = self.settings.get("conda", {})
        dump_data = {
            "sources": self.settings.get("source", []),
            "dependencies": self.metadata.get("dependencies", []),
            "dev-dependencies": self.settings.get("dev-dependencies", {}),
            "optional-dependencies": self.metadata.get("optional-dependencies", {}),
            "requires-python": self.metadata.get("requires-python", ""),
            "pdm-conda": {
                "channels": pdm_conda_data.get("channels", []),
                "as-default-manager": pdm_conda_data.get("as-default-manager", False),
                "excludes": pdm_conda_data.get("excludes", []),
                "dependencies": pdm_conda_data.get("dependencies", []),
                "dev-dependencies": pdm_conda_data.get("dev-dependencies", {}),
                "optional-dependencies": pdm_conda_data.get("optional-dependencies", {}),
            },
            "overrides": self.resolution_overrides,
        }
        pyproject_content = json.dumps(dump_data, sort_keys=True)
        hasher = hashlib.new(algo)
        hasher.update(pyproject_content.encode("utf-8"))
        return hasher.hexdigest()
