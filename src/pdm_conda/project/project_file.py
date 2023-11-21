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
        pdm_conda_data = self.settings.get("conda", dict())
        pdm_conda_dump_data = dict()
        for hash_config in (
            "channels",
            "as-default-manager",
            "excludes",
            "dependencies",
            "dev-dependencies",
            "optional-dependencies",
        ):
            if hash_config in pdm_conda_data:
                pdm_conda_dump_data[hash_config] = pdm_conda_data[hash_config]
        if not pdm_conda_dump_data:
            return super().content_hash(algo)

        dump_data = {
            "sources": self.settings.get("source", []),
            "dependencies": self.metadata.get("dependencies", []),
            "dev-dependencies": self.settings.get("dev-dependencies", {}),
            "optional-dependencies": self.metadata.get("optional-dependencies", {}),
            "requires-python": self.metadata.get("requires-python", ""),
            "pdm-conda": pdm_conda_dump_data,
            "overrides": self.resolution_overrides,
        }
        pyproject_content = json.dumps(dump_data, sort_keys=True)
        hasher = hashlib.new(algo)
        hasher.update(pyproject_content.encode("utf-8"))
        return hasher.hexdigest()
