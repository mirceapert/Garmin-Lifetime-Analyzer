"""Walk a Garmin export: a .zip, an extracted folder, or a folder of zips. Nested zips are opened in place."""
from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExportEntry:
    name: str          # path inside the export, e.g. DI_CONNECT/DI-Connect-Uploaded-Files/UploadedFiles_0-_Part1.zip/1234.fit
    data: bytes

    @property
    def basename(self) -> str:
        return self.name.rsplit("/", 1)[-1]

    @property
    def suffix(self) -> str:
        b = self.basename.lower()
        return b[b.rfind("."):] if "." in b else ""


def _from_zip(zf: zipfile.ZipFile, prefix: str) -> Iterator[ExportEntry]:
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = f"{prefix}{info.filename}"
        with zf.open(info) as fh:
            data = fh.read()
        if info.filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as inner:
                    yield from _from_zip(inner, name + "/")
                continue
            except zipfile.BadZipFile:
                pass
        yield ExportEntry(name, data)


def iter_export(path: Path) -> Iterator[ExportEntry]:
    path = Path(path)
    if path.is_file():
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as zf:
                yield from _from_zip(zf, "")
        else:
            yield ExportEntry(path.name, path.read_bytes())
        return
    for p in sorted(path.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(path).as_posix()
        if p.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(p) as zf:
                    yield from _from_zip(zf, rel + "/")
                continue
            except zipfile.BadZipFile:
                pass
        yield ExportEntry(rel, p.read_bytes())
