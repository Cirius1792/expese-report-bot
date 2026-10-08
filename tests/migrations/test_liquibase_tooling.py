"""Guard rails for the Liquibase tooling configuration (ADR 0013).

Liquibase 5.x dropped bundled JDBC drivers and relies on the unreliable `lpm`
package manager; this project therefore pins the official `liquibase/liquibase`
**4.33.0** image, the last release line that bundles the SQLite JDBC driver.
These tests keep the image pin consistent across every call site and assert the
jar-free invariant: no `lib/` driver jars, no `--classpath`.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
LIQUIBASE_IMAGE = "liquibase/liquibase:4.33.0"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_wrapper_pins_bundled_driver_image_without_classpath() -> None:
    script = _read("scripts/liquibase")
    assert LIQUIBASE_IMAGE in script
    # The flag is always passed as --classpath=<jars>; prose comments may name it.
    assert "--classpath=" not in script


def test_entrypoint_needs_no_classpath() -> None:
    entrypoint = _read("docker-entrypoint.sh")
    assert "--classpath=" not in entrypoint
    assert "update" in entrypoint


def test_dockerfile_bases_on_bundled_driver_image_without_lib_copy() -> None:
    dockerfile = _read("Dockerfile")
    assert f"FROM {LIQUIBASE_IMAGE}" in dockerfile
    assert "COPY lib/" not in dockerfile


def _workflows_text() -> str:
    workflows = REPO_ROOT / ".github" / "workflows"
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(workflows.glob("*.yml")))


def test_workflows_pin_bundled_driver_image() -> None:
    workflows = _workflows_text()
    assert f"docker pull {LIQUIBASE_IMAGE}" in workflows
    assert "liquibase/liquibase:5.0.4" not in workflows


def test_no_committed_driver_jars() -> None:
    lib = REPO_ROOT / "lib"
    jars = sorted(p.name for p in lib.glob("*.jar")) if lib.is_dir() else []
    assert jars == []
