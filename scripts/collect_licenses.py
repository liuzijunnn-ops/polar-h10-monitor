"""Collect installed distribution license texts for a portable build.

Run from the repository root before PyInstaller. Does not read recordings.
"""
from importlib import metadata
import json
from pathlib import Path
import shutil


def main():
    destination = Path(__file__).resolve().parents[1] / "build" / "dependency-licenses"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    inventory = []
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        package_dir = destination / name
        package_dir.mkdir()
        record = {
            "name": name, "version": dist.version,
            "license_expression": dist.metadata.get("License-Expression"),
            "license": dist.metadata.get("License"),
            "home_page": dist.metadata.get("Home-page"),
            "project_urls": dist.metadata.get_all("Project-URL") or [],
            "license_files": [],
        }
        (package_dir / "METADATA.txt").write_text(dist.read_text("METADATA") or dist.read_text("PKG-INFO") or "", encoding="utf-8")
        for entry in dist.files or []:
            path = Path(str(entry))
            if not any(part.lower().startswith(("license", "licence", "copying", "notice", "copyright")) for part in path.parts):
                continue
            source = Path(dist.locate_file(entry))
            if not source.is_file():
                continue
            # Distribution records can contain ../../ paths; never reproduce those.
            safe_parts = [part for part in path.parts if part not in ("..", ".", path.anchor)]
            target = package_dir.joinpath(*safe_parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            record["license_files"].append(str(target.relative_to(destination)))
        inventory.append(record)
    (destination / "INDEX.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Collected notices for {len(inventory)} installed distributions in {destination}")


if __name__ == "__main__":
    main()
