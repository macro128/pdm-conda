import hashlib
import json

from pdm.project.project_file import PyProject as PyProjectBase


def _remove_empty_groups(doc: dict) -> None:
    for k, v in list(doc.items()):
        if isinstance(v, list) and not v:
            del doc[k]


class PyProject(PyProjectBase):
    def write(self, show_message: bool = True) -> None:
        _remove_empty_groups(self._data.get("project", {}).get("optional-dependencies", {}))
        _remove_empty_groups(
            self._data.get("tool", {}).get("pdm", {}).get("conda", {}).get("optional-dependencies", {}),
        )
        super().write(show_message)

    def content_hash(self, algo: str = "sha256") -> str:
        """Generate a hash of the sensible content of the pyproject.toml file. When the hash changes, it means the
        project needs to be relocked.

        :param algo: hash algorithm name
        :return: pyproject.toml hash
        """
        pdm_conda_data = self.settings.get("conda", {})
        pdm_conda_dump_data = {}
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
            "overrides": self.resolution.get("overrides", {}),
        }
        pyproject_content = json.dumps(dump_data, sort_keys=True)
        hasher = hashlib.new(algo)
        hasher.update(pyproject_content.encode("utf-8"))
        return hasher.hexdigest()
