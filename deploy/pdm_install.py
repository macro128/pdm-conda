import argparse
import itertools
import os
import subprocess


def get_pdm_executable() -> str:
    """
    Get local PDM executable path
    :return: PDM path
    """
    exc = RuntimeError("pdm local executable not found")

    try:
        path_process = subprocess.run(
            ["which", "pdm"],
            check=True,
            capture_output=True,
            encoding="utf8",
        )
    except Exception as e:
        raise exc from e

    path = path_process.stdout.strip()
    if not path:
        raise exc

    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Execute PDM install with some arguments overrides.",
    )
    parser.add_argument(
        "-G",
        "--groups",
        nargs="*",
        default="",
        help="select groups of optional-dependencies",
    )
    parser.add_argument(
        "-",
        dest="args",
        nargs=argparse.REMAINDER,
        help="args to pass to pdm install",
    )
    args = parser.parse_args()

    groups = list(itertools.chain.from_iterable(g.split(",") for g in args.groups))
    groups = [f"-G {g.strip()}" for g in groups if g.strip()]

    args = args.args + groups
    # replace current process with pdm install
    os.execl(get_pdm_executable(), "pdm", "install", *args)
