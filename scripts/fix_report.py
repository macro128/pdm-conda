import os
from pathlib import Path

if __name__ == "__main__":
    if (local_path := os.getenv("LOCAL_PATH", None)) is not None:
        coverage_file = Path("coverage.xml")

        with coverage_file.open("r+") as f:
            contents = f.read().replace("/app/", f"{local_path}/")
            f.seek(0)
            f.write(contents)
