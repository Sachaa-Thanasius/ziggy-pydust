"""
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import functools
import importlib.metadata
from pathlib import Path
from typing import Any, TypeVar

import tomllib

T = TypeVar("T")


def _validate_input_type(name: str, inp: T, typ: Any) -> T:
    if isinstance(inp, typ):
        return inp

    msg = f'Input of {name}={inp!r} is not a valid "{typ}".'
    raise TypeError(msg)


class ExtModule:
    """Config for a single Zig extension module."""

    def __init__(self, *, name: str, root: Path, limited_api: bool = True) -> None:
        self.name = _validate_input_type("name", name, str)
        self.root = _validate_input_type("root", root, Path)
        self.limited_api = _validate_input_type("limited_api", limited_api, bool)

    @property
    def libname(self) -> str:
        return self.name.rsplit(".", maxsplit=1)[-1]

    @property
    def install_path(self) -> Path:
        # FIXME(ngates): for non-limited API
        if not self.limited_api:
            msg = "Only limited API modules are supported right now"
            raise NotImplementedError(msg)
        return Path(*self.name.split(".")).with_suffix(".abi3.so")

    @property
    def test_bin(self) -> Path:
        return (Path("zig-out") / "bin" / self.libname).with_suffix(".test.bin")


class ToolPydust:
    """Model for tool.pydust section of a pyproject.toml."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        zig_exe: Path | None = None,
        build_zig: Path = Path("build.zig"),
        zig_tests: bool = True,
        self_managed: bool = False,
        ext_module: list[ExtModule] | None = None,
    ) -> None:
        self.zig_exe = _validate_input_type("zig_exe", zig_exe, Path | None)
        self.build_zig = _validate_input_type("build_zig", build_zig, Path)

        # Whether to include Zig tests as part of the pytest collection.
        self.zig_tests = _validate_input_type("zig_tests", zig_tests, bool)

        # When true, python module definitions are configured by the user in their own build.zig file.
        # When false, ext_modules is used to auto-generated a build.zig file.
        self.self_managed = _validate_input_type("self_managed", self_managed, bool)

        # We rename pluralized config sections so the pyproject.toml reads better.
        if ext_module is None:
            self.ext_modules = []
        else:
            self.ext_modules = _validate_input_type("ext_module", ext_module, list)

        # Final validation.
        if self.self_managed and self.ext_modules:
            msg = "ext_modules cannot be defined when using Pydust in self-managed mode."
            raise ValueError(msg)

    @property
    def pydust_build_zig(self) -> Path:
        return self.build_zig.parent / "pydust.build.zig"


@functools.lru_cache(1)
def load() -> ToolPydust:
    with Path("pyproject.toml").open(mode="rb") as f:
        pyproject = tomllib.load(f)

    # Since Poetry doesn't support locking the build-system.requires dependencies,
    # we perform a check here to prevent the versions from diverging.
    pydust_version = importlib.metadata.version("ziggy-pydust")

    # Skip 0.1.0 as it's the development version when installed locally.
    if pydust_version != "0.1.0":
        for req in pyproject["build-system"]["requires"]:
            if not req.startswith("ziggy-pydust"):
                continue
            expected = f"ziggy-pydust=={pydust_version}"
            if req != expected:
                msg = (
                    "Detected misconfigured ziggy-pydust. "
                    f'You must include "{expected}" in build-system.requires in pyproject.toml'
                )
                raise ValueError(msg)

    return ToolPydust(**pyproject["tool"].get("pydust", {}))
