import re

from pdm.cli import utils
from pdm.installers import synchronizers
from pdm.models import candidates, repositories, requirements, working_set


def normalize_name(name: str, lowercase: bool = True) -> str:
    """Normalize name and keep `_`.

    :param name: name to normalize
    :param lowercase: if true lowercase name
    :return: normalized name
    """
    name = re.sub(r"[^A-Za-z0-9._]+", "-", name)
    return name.lower() if lowercase else name


for m in [utils, synchronizers, candidates, requirements, repositories, working_set]:
    m.normalize_name = normalize_name
