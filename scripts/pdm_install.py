import argparse
import itertools
import os
import subprocess


def get_pdm_executable() -> str:
    """Get local PDM executable path.

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


def parse_list(args):
    return list(itertools.chain.from_iterable(elem.split(",") for elem in args))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Execute PDM install with some arguments overrides.",
    )
    parser.add_argument(
        "pdm_executable",
        nargs="?",
        help="args to pass to pdm install",
    )
    parser.add_argument(
        "-G",
        "--groups",
        nargs="*",
        default="",
        help="select groups of optional-dependencies",
    )
    parser.add_argument(
        "--lib",
        action="store_false",
        dest="app",
    )
    parser.add_argument(
        "--app",
        action="store_true",
        dest="app",
    )
    parser.add_argument(
        "-",
        dest="args",
        default=[],
        nargs=argparse.REMAINDER,
        help="args to pass to pdm install",
    )
    parser.set_defaults(app=False)
    args = parser.parse_args()

    groups = parse_list(args.groups)
    groups = [f"-G {g.strip()}" for g in groups if g.strip()]

    cmd_args = args.args + groups
    extra_args = []
    if "--prod" in cmd_args:
        extra_args += ["--no-editable", "--frozen-lockfile", "--check"]
    elif "--dev" in cmd_args:
        extra_args.append("-vv")
    if args.app:
        extra_args.append("--no-self")

    for arg in extra_args:
        if arg not in cmd_args:
            cmd_args.append(arg)

    # replace current process with pdm install
    os.execl(args.pdm_executable or get_pdm_executable(), "pdm", "install", *cmd_args)
