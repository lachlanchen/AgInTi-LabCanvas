#!/usr/bin/env python3
"""Safely extract readable evidence from WeChat documents and archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any
import xml.etree.ElementTree as ET
import zipfile


READABLE_STATUSES = {"readable", "partial"}
TEXT_SUFFIXES = {
    ".bib",
    ".c",
    ".cc",
    ".cfg",
    ".cpp",
    ".csv",
    ".go",
    ".h",
    ".hpp",
    ".htm",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".log",
    ".md",
    ".markdown",
    ".m",
    ".py",
    ".r",
    ".rst",
    ".rtf",
    ".sh",
    ".tex",
    ".toml",
    ".ts",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
DOCUMENT_SUFFIXES = TEXT_SUFFIXES | {".7z", ".doc", ".docx", ".pdf", ".rar", ".zip"}
EXECUTABLE_SUFFIXES = {
    ".appimage",
    ".bat",
    ".bin",
    ".cmd",
    ".com",
    ".dll",
    ".dylib",
    ".exe",
    ".msi",
    ".scr",
    ".so",
}


def default_limits() -> dict[str, int | float]:
    return {
        "max_source_bytes": env_int("WECHAT_DOCUMENT_MAX_SOURCE_BYTES", 200 * 1024 * 1024),
        "max_text_chars": env_int("WECHAT_DOCUMENT_MAX_TEXT_CHARS", 2_000_000),
        "max_archive_members": env_int("WECHAT_DOCUMENT_MAX_ARCHIVE_MEMBERS", 240),
        "max_archive_total_bytes": env_int("WECHAT_DOCUMENT_MAX_ARCHIVE_BYTES", 200 * 1024 * 1024),
        "max_archive_member_bytes": env_int("WECHAT_DOCUMENT_MAX_MEMBER_BYTES", 50 * 1024 * 1024),
        "max_archive_ratio": env_float("WECHAT_DOCUMENT_MAX_COMPRESSION_RATIO", 250.0),
        "max_archive_depth": env_int("WECHAT_DOCUMENT_MAX_ARCHIVE_DEPTH", 2),
        "max_ocr_pages": env_int("WECHAT_DOCUMENT_MAX_OCR_PAGES", 10),
        "command_timeout_seconds": env_int("WECHAT_DOCUMENT_COMMAND_TIMEOUT_SECONDS", 120),
    }


def env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.environ.get(name, str(default))))
    except ValueError:
        return default


def is_document_candidate(path: Path) -> bool:
    if path.suffix.lower() in DOCUMENT_SUFFIXES:
        return True
    return detect_document_kind(path) in {"pdf", "docx", "legacy_word", "zip", "rar", "7z", "text"}


def analyze_document(
    source: Path,
    output_dir: Path,
    *,
    limits: dict[str, int | float] | None = None,
    archive_depth: int = 0,
) -> dict[str, Any]:
    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    active_limits = dict(default_limits() if limits is None else limits)
    result: dict[str, Any] = {
        "status": "failed",
        "source_path": str(source),
        "filename": source.name,
        "suffix": source.suffix.lower(),
        "read_only": True,
        "executed_content": False,
        "archive_depth": archive_depth,
        "warnings": [],
    }
    if not source.is_file():
        result.update(status="missing", error="source file does not exist")
        return finalize_result(result, output_dir, active_limits)
    size = source.stat().st_size
    result["size_bytes"] = size
    result["sha256"] = sha256_file(source)
    if size > int(active_limits["max_source_bytes"]):
        result.update(status="oversized", error="source exceeds configured read limit")
        return finalize_result(result, output_dir, active_limits)

    kind = detect_document_kind(source)
    result["kind"] = kind
    try:
        if kind == "pdf":
            result.update(read_pdf(source, output_dir, active_limits))
        elif kind == "docx":
            result.update(read_docx(source, active_limits))
        elif kind == "legacy_word":
            result.update(read_legacy_word(source, output_dir, active_limits))
        elif kind == "zip":
            result.update(read_zip_archive(source, output_dir, active_limits, archive_depth=archive_depth))
        elif kind in {"rar", "7z"}:
            result.update(read_external_archive(source, output_dir, active_limits, archive_depth=archive_depth, kind=kind))
        elif kind == "text":
            result.update(read_text_file(source, active_limits))
        else:
            result.update(status="unsupported", error="unsupported document format")
    except (OSError, ET.ParseError, zipfile.BadZipFile, RuntimeError) as exc:
        result.update(status="failed", error=f"{type(exc).__name__}: {str(exc)[:500]}")
    return finalize_result(result, output_dir, active_limits)


def detect_document_kind(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            head = handle.read(16)
    except OSError:
        return "unsupported"
    suffix = path.suffix.lower()
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "legacy_word" if suffix in {".doc", ".docx"} else "unsupported"
    if head.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")):
        return "rar"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    if zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except (OSError, zipfile.BadZipFile):
            return "unsupported"
        if "[Content_Types].xml" in names and "word/document.xml" in names:
            return "docx"
        return "zip"
    if suffix in TEXT_SUFFIXES:
        return "text"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".doc":
        return "legacy_word"
    if suffix in {".rar", ".7z"}:
        return suffix.lstrip(".")
    return "unsupported"


def read_text_file(path: Path, limits: dict[str, int | float]) -> dict[str, Any]:
    data, source_truncated = read_limited_bytes(path, int(limits["max_text_chars"]) * 4)
    text, encoding = decode_text_bytes(data)
    if not text.strip():
        return {"status": "unreadable", "method": "text-decode", "encoding": encoding, "error": "no readable text"}
    return {
        "status": "partial" if source_truncated else "readable",
        "method": "text-decode",
        "encoding": encoding,
        "source_truncated": source_truncated,
        "text": bound_text(text, int(limits["max_text_chars"])),
    }


def decode_text_bytes(data: bytes) -> tuple[str, str]:
    if not data:
        return "", "empty"
    encodings = []
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.extend(["utf-16", "utf-16-le", "utf-16-be"])
    elif data.startswith(b"\xef\xbb\xbf"):
        encodings.append("utf-8-sig")
    encodings.extend(["utf-8", "gb18030", "big5", "shift_jis", "cp1252"])
    for encoding in encodings:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" in text and not encoding.startswith("utf-16"):
            continue
        printable = sum(char.isprintable() or char in "\n\r\t" for char in text)
        if printable / max(1, len(text)) >= 0.82:
            return normalize_text(text), encoding
    return "", "unknown"


def read_docx(path: Path, limits: dict[str, int | float]) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        infos = {item.filename: item for item in archive.infolist()}
        if len(infos) > int(limits["max_archive_members"]):
            return {"status": "oversized", "method": "docx-xml", "error": "DOCX has too many package members"}
        if sum(item.file_size for item in infos.values()) > int(limits["max_archive_total_bytes"]):
            return {"status": "oversized", "method": "docx-xml", "error": "DOCX package exceeds uncompressed byte limit"}
        encrypted = [name for name, item in infos.items() if item.flag_bits & 0x1]
        if encrypted:
            return {"status": "encrypted", "method": "docx-xml", "error": "encrypted DOCX members"}
        required = infos.get("word/document.xml")
        if required is None:
            return {"status": "unreadable", "method": "docx-xml", "error": "word/document.xml is missing"}
        reason = unsafe_package_member_reason(required, limits)
        if reason:
            return {"status": "oversized", "method": "docx-xml", "error": f"unsafe main document member: {reason}"}
        document = archive.read("word/document.xml")
        parts = [extract_word_xml(document)]
        extra_names = sorted(
            name
            for name in infos
            if re.fullmatch(r"word/(?:header|footer)\d+\.xml", name)
            or name in {"word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"}
        )
        for name in extra_names:
            if unsafe_package_member_reason(infos[name], limits):
                continue
            extracted = extract_word_xml(archive.read(name))
            if extracted:
                parts.append(f"\n[{name}]\n{extracted}")
        metadata = extract_docx_metadata(archive, limits)
        media = sorted(name for name in infos if name.startswith("word/media/") and not name.endswith("/"))
    text = normalize_text("\n".join(part for part in parts if part.strip()))
    if not text:
        return {"status": "unreadable", "method": "docx-xml", "metadata": metadata, "error": "DOCX contains no readable text"}
    return {
        "status": "readable",
        "method": "docx-xml",
        "metadata": metadata,
        "embedded_media_count": len(media),
        "embedded_media": media[:80],
        "text": bound_text(text, int(limits["max_text_chars"])),
    }


def extract_word_xml(data: bytes) -> str:
    root = parse_xml_safely(data)
    lines: list[str] = []
    for paragraph in root.iter():
        if local_name(paragraph.tag) != "p":
            continue
        pieces: list[str] = []
        for node in paragraph.iter():
            name = local_name(node.tag)
            if name in {"t", "instrText", "delText"} and node.text:
                pieces.append(node.text)
            elif name == "tab":
                pieces.append("\t")
            elif name in {"br", "cr"}:
                pieces.append("\n")
        line = "".join(pieces).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract_docx_metadata(archive: zipfile.ZipFile, limits: dict[str, int | float]) -> dict[str, str]:
    if "docProps/core.xml" not in archive.namelist():
        return {}
    info = archive.getinfo("docProps/core.xml")
    if unsafe_package_member_reason(info, limits):
        return {}
    try:
        root = parse_xml_safely(archive.read("docProps/core.xml"))
    except (ET.ParseError, KeyError, RuntimeError):
        return {}
    accepted = {"title", "subject", "creator", "description", "keywords", "created", "modified", "lastModifiedBy"}
    result: dict[str, str] = {}
    for node in root.iter():
        name = local_name(node.tag)
        value = str(node.text or "").strip()
        if name in accepted and value:
            result[name] = value
    return result


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_xml_safely(data: bytes) -> ET.Element:
    # Removing NUL bytes also exposes declaration tokens in UTF-16 XML.
    upper = data.upper().replace(b"\x00", b"")
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise RuntimeError("XML DTD/entity declarations are not allowed")
    return ET.fromstring(data)


def read_pdf(path: Path, output_dir: Path, limits: dict[str, int | float]) -> dict[str, Any]:
    info = pdf_info(path, int(limits["command_timeout_seconds"]))
    if str(info.get("encrypted") or "").lower().startswith("yes"):
        return {"status": "encrypted", "method": "pdfinfo", "pdf_info": info, "error": "PDF is encrypted"}
    pdftotext = shutil.which("pdftotext")
    extracted = output_dir / "pdftotext.txt"
    text = ""
    pdf_text_truncated = False
    errors: list[str] = []
    if pdftotext:
        proc = run_external(
            [pdftotext, "-layout", "-nopgbrk", str(path), str(extracted)],
            timeout=int(limits["command_timeout_seconds"]),
        )
        if proc.returncode == 0 and extracted.is_file():
            data, pdf_text_truncated = read_limited_bytes(extracted, int(limits["max_text_chars"]) * 4)
            text, _ = decode_text_bytes(data)
            if pdf_text_truncated:
                errors.append("pdftotext output was truncated at the configured text limit")
        elif proc.stderr.strip():
            errors.append(proc.stderr.strip()[:500])
    else:
        errors.append("pdftotext is not installed")
    if substantial_pdf_text(text, info):
        return {
            "status": "partial" if pdf_text_truncated else "readable",
            "method": "pdftotext",
            "pdf_info": info,
            "page_count": int_or_none(info.get("pages")),
            "text": bound_text(text, int(limits["max_text_chars"])),
            "warnings": errors,
        }

    ocr = ocr_pdf(path, output_dir, info, limits)
    ocr_text = str(ocr.pop("text", ""))
    if ocr_text.strip():
        merged = text.strip()
        if merged:
            merged += "\n\n[OCR supplement]\n"
        merged += ocr_text
        status = "partial" if ocr.get("pages_truncated") else "readable"
        return {
            "status": status,
            "method": "pdftotext+ocr" if text.strip() else "pdf-ocr",
            "pdf_info": info,
            "page_count": int_or_none(info.get("pages")),
            "text": bound_text(merged, int(limits["max_text_chars"])),
            "warnings": errors + list(ocr.get("warnings") or []),
            **ocr,
        }
    return {
        "status": "unreadable",
        "method": "pdftotext+ocr",
        "pdf_info": info,
        "page_count": int_or_none(info.get("pages")),
        "warnings": errors + list(ocr.get("warnings") or []),
        "error": "no readable PDF text was extracted",
    }


def pdf_info(path: Path, timeout: int) -> dict[str, str]:
    tool = shutil.which("pdfinfo")
    if not tool:
        return {}
    proc = run_external([tool, str(path)], timeout=timeout)
    if proc.returncode != 0:
        return {}
    info: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        info[safe_key(key)] = value.strip()
    return info


def substantial_pdf_text(text: str, info: dict[str, str]) -> bool:
    visible = re.sub(r"\s+", "", text)
    pages = int_or_none(info.get("pages")) or 1
    return len(visible) >= max(80, min(1200, pages * 20))


def ocr_pdf(path: Path, output_dir: Path, info: dict[str, str], limits: dict[str, int | float]) -> dict[str, Any]:
    pdftoppm = shutil.which("pdftoppm")
    tesseract = shutil.which("tesseract")
    if not pdftoppm or not tesseract:
        return {"warnings": ["PDF OCR tools are unavailable"], "preview_images": []}
    total_pages = int_or_none(info.get("pages")) or int(limits["max_ocr_pages"])
    page_limit = min(total_pages, int(limits["max_ocr_pages"]))
    page_dir = output_dir / "ocr_pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    prefix = page_dir / "page"
    proc = run_external(
        [pdftoppm, "-f", "1", "-l", str(page_limit), "-r", "170", "-png", str(path), str(prefix)],
        timeout=max(int(limits["command_timeout_seconds"]), page_limit * 20),
    )
    if proc.returncode != 0:
        return {"warnings": [proc.stderr.strip()[:500] or "pdftoppm failed"], "preview_images": []}
    pages = sorted(page_dir.glob("page-*.png"), key=pdf_page_number)
    languages = tesseract_languages()
    text_parts: list[str] = []
    warnings: list[str] = []
    for index, image in enumerate(pages, start=1):
        command = [tesseract, str(image), "stdout"]
        if languages:
            command += ["-l", languages]
        command += ["--psm", "3"]
        ocr = run_external(command, timeout=max(30, int(limits["command_timeout_seconds"])))
        if ocr.returncode == 0 and ocr.stdout.strip():
            text_parts.append(f"[Page {index}]\n{ocr.stdout.strip()}")
        elif ocr.stderr.strip():
            warnings.append(f"page {index}: {ocr.stderr.strip()[:240]}")
    return {
        "text": normalize_text("\n\n".join(text_parts)),
        "ocr_pages": len(pages),
        "pages_truncated": total_pages > page_limit,
        "preview_images": [str(item) for item in pages[:3]],
        "warnings": warnings,
    }


def tesseract_languages() -> str:
    configured = os.environ.get("WECHAT_DOCUMENT_OCR_LANGS", "").strip()
    if configured:
        return configured
    tool = shutil.which("tesseract")
    if not tool:
        return ""
    proc = run_external([tool, "--list-langs"], timeout=10)
    available = {line.strip() for line in proc.stdout.splitlines() if line.strip() and not line.startswith("List of")}
    selected = [name for name in ("eng", "chi_sim", "chi_tra", "jpn") if name in available]
    return "+".join(selected)


def pdf_page_number(path: Path) -> int:
    match = re.search(r"(\d+)$", path.stem)
    return int(match.group(1)) if match else 0


def read_legacy_word(path: Path, output_dir: Path, limits: dict[str, int | float]) -> dict[str, Any]:
    antiword = shutil.which("antiword")
    if antiword:
        proc = run_external([antiword, str(path)], timeout=int(limits["command_timeout_seconds"]))
        if proc.returncode == 0 and proc.stdout.strip():
            return {
                "status": "readable",
                "method": "antiword",
                "text": bound_text(normalize_text(proc.stdout), int(limits["max_text_chars"])),
            }
    office = shutil.which("libreoffice") or shutil.which("soffice")
    if not office:
        return {"status": "unreadable", "method": "legacy-word", "error": "antiword/LibreOffice is unavailable"}
    convert_dir = output_dir / "legacy_word_conversion"
    profile_dir = output_dir / "libreoffice_profile"
    convert_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)
    command = [
        office,
        "--headless",
        "--safe-mode",
        "--nologo",
        "--nodefault",
        "--nolockcheck",
        "--norestore",
        f"-env:UserInstallation={profile_dir.as_uri()}",
        "--convert-to",
        "txt:Text",
        "--outdir",
        str(convert_dir),
        str(path),
    ]
    env = os.environ.copy()
    env["HOME"] = str(profile_dir)
    proc = run_external(command, timeout=int(limits["command_timeout_seconds"]), env=env)
    outputs = sorted(convert_dir.glob("*.txt"))
    if proc.returncode == 0 and outputs:
        data, output_truncated = read_limited_bytes(outputs[0], int(limits["max_text_chars"]) * 4)
        text, encoding = decode_text_bytes(data)
        if text.strip():
            return {
                "status": "partial" if output_truncated else "readable",
                "method": "libreoffice-headless-safe-mode",
                "encoding": encoding,
                "source_truncated": output_truncated,
                "text": bound_text(text, int(limits["max_text_chars"])),
            }
    return {
        "status": "unreadable",
        "method": "libreoffice-headless-safe-mode",
        "error": proc.stderr.strip()[:500] or proc.stdout.strip()[:500] or "legacy Word conversion failed",
    }


def read_zip_archive(
    path: Path,
    output_dir: Path,
    limits: dict[str, int | float],
    *,
    archive_depth: int,
) -> dict[str, Any]:
    if archive_depth >= int(limits["max_archive_depth"]):
        return {"status": "unsupported", "method": "safe-zip", "error": "maximum nested archive depth reached"}
    extract_root = output_dir / "archive_files"
    analysis_root = output_dir / "archive_analysis"
    extract_root.mkdir(parents=True, exist_ok=True)
    analysis_root.mkdir(parents=True, exist_ok=True)
    members: list[dict[str, Any]] = []
    readable: list[dict[str, Any]] = []
    total_uncompressed = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > int(limits["max_archive_members"]):
            return {
                "status": "oversized",
                "method": "safe-zip",
                "member_count": len(infos),
                "error": "archive has too many members",
            }
        for index, info in enumerate(infos, start=1):
            entry: dict[str, Any] = {
                "name": info.filename,
                "size_bytes": info.file_size,
                "compressed_bytes": info.compress_size,
            }
            members.append(entry)
            if info.is_dir():
                entry["status"] = "directory"
                continue
            reason = unsafe_zip_member_reason(info, extract_root, limits, total_uncompressed)
            if reason:
                entry.update(status="skipped", reason=reason)
                continue
            total_uncompressed += info.file_size
            relative = PurePosixPath(info.filename)
            target = extract_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = archive.read(info)
            except (RuntimeError, zipfile.BadZipFile) as exc:
                entry.update(status="skipped", reason=f"read-failed:{type(exc).__name__}")
                continue
            target.write_bytes(data)
            entry.update(status="extracted", extracted_path=str(target))
            if not is_document_candidate(target) and detect_document_kind(target) == "unsupported":
                entry["read_status"] = "inventory-only"
                continue
            child_dir = analysis_root / f"{index:03d}-{safe_slug(target.stem)}"
            child = analyze_document(target, child_dir, limits=limits, archive_depth=archive_depth + 1)
            entry["read_status"] = child.get("status")
            entry["analysis_manifest"] = child.get("manifest_json")
            entry["text_path"] = child.get("text_path")
            if child.get("status") in READABLE_STATUSES:
                readable.append(
                    {
                        "name": info.filename,
                        "status": child.get("status"),
                        "kind": child.get("kind"),
                        "text_path": child.get("text_path"),
                        "text_preview": child.get("text_preview"),
                    }
                )
    skipped = [item for item in members if item.get("status") == "skipped"]
    safe_files = [item for item in members if item.get("status") == "extracted"]
    inventory = archive_inventory_text(path.name, members, readable)
    if readable:
        status = "partial" if skipped else "readable"
    elif safe_files:
        status = "partial" if skipped else "readable"
    else:
        status = "unreadable"
    return {
        "status": status,
        "method": "safe-zip",
        "member_count": len(members),
        "readable_member_count": len(readable),
        "total_uncompressed_bytes": total_uncompressed,
        "members": members,
        "readable_members": readable,
        "text": bound_text(inventory, int(limits["max_text_chars"])),
        "warnings": [f"{len(skipped)} archive member(s) were safely skipped"] if skipped else [],
    }


def read_external_archive(
    path: Path,
    output_dir: Path,
    limits: dict[str, int | float],
    *,
    archive_depth: int,
    kind: str,
) -> dict[str, Any]:
    method = f"safe-{kind}-via-7z"
    if archive_depth >= int(limits["max_archive_depth"]):
        return {"status": "unsupported", "method": method, "error": "maximum nested archive depth reached"}
    tool = shutil.which("7zz") or shutil.which("7z")
    if not tool:
        return {"status": "unsupported", "method": method, "error": "7z command is not installed"}
    fallback_tool = shutil.which("bsdtar") if kind == "rar" else None
    try:
        listed = subprocess.run(
            [tool, "l", "-slt", "-ba", "--", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=float(limits["command_timeout_seconds"]),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "method": method, "error": f"archive listing failed: {type(exc).__name__}"}
    if listed.returncode != 0:
        return {"status": "failed", "method": method, "error": listed.stderr.strip()[:500] or "archive listing failed"}
    records = parse_7z_slt(listed.stdout)
    if len(records) > int(limits["max_archive_members"]):
        return {
            "status": "oversized",
            "method": method,
            "member_count": len(records),
            "error": "archive has too many members",
        }
    extract_root = output_dir / "archive_files"
    analysis_root = output_dir / "archive_analysis"
    extract_root.mkdir(parents=True, exist_ok=True)
    analysis_root.mkdir(parents=True, exist_ok=True)
    members: list[dict[str, Any]] = []
    readable: list[dict[str, Any]] = []
    total_uncompressed = 0
    for index, record in enumerate(records, start=1):
        name = str(record.get("Path") or "")
        size = integer_field(record.get("Size"))
        packed_size = integer_field(record.get("Packed Size"))
        is_dir = str(record.get("Folder") or "").strip() == "+"
        entry: dict[str, Any] = {
            "name": name,
            "size_bytes": size,
            "compressed_bytes": packed_size,
        }
        members.append(entry)
        if is_dir:
            entry["status"] = "directory"
            continue
        reason = unsafe_external_archive_member_reason(record, extract_root, limits, total_uncompressed)
        if reason:
            entry.update(status="skipped", reason=reason)
            continue
        total_uncompressed += size
        if Path(name).suffix.lower() not in DOCUMENT_SUFFIXES:
            entry.update(status="listed", read_status="inventory-only")
            continue
        relative = PurePosixPath(name)
        target = extract_root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        extracted_bytes, extraction_tool, extraction_error = extract_external_archive_member(
            path,
            name,
            primary_tool=tool,
            fallback_tool=fallback_tool,
            timeout=float(limits["command_timeout_seconds"]),
        )
        if extracted_bytes is None:
            entry.update(status="skipped", reason=f"extract-failed:{extraction_error[:240]}")
            continue
        if len(extracted_bytes) > int(limits["max_archive_member_bytes"]):
            entry.update(status="skipped", reason="member-too-large-after-extract")
            continue
        target.write_bytes(extracted_bytes)
        entry.update(status="extracted", extracted_path=str(target), extraction_tool=extraction_tool)
        child_dir = analysis_root / f"{index:03d}-{safe_slug(target.stem)}"
        child = analyze_document(target, child_dir, limits=limits, archive_depth=archive_depth + 1)
        entry["read_status"] = child.get("status")
        entry["analysis_manifest"] = child.get("manifest_json")
        entry["text_path"] = child.get("text_path")
        if child.get("status") in READABLE_STATUSES:
            readable.append(
                {
                    "name": name,
                    "status": child.get("status"),
                    "kind": child.get("kind"),
                    "text_path": child.get("text_path"),
                    "text_preview": child.get("text_preview"),
                }
            )
    skipped = [item for item in members if item.get("status") == "skipped"]
    inventory = archive_inventory_text(path.name, members, readable)
    status = "partial" if skipped else "readable"
    if not members:
        status = "unreadable"
    return {
        "status": status,
        "method": method,
        "member_count": len(members),
        "readable_member_count": len(readable),
        "total_uncompressed_bytes": total_uncompressed,
        "members": members,
        "readable_members": readable,
        "text": bound_text(inventory, int(limits["max_text_chars"])),
        "warnings": [f"{len(skipped)} archive member(s) were safely skipped"] if skipped else [],
    }


def extract_external_archive_member(
    archive: Path,
    member: str,
    *,
    primary_tool: str,
    fallback_tool: str | None,
    timeout: float,
) -> tuple[bytes | None, str, str]:
    commands = [("7z", [primary_tool, "x", "-so", "-y", "--", str(archive), member])]
    if fallback_tool:
        commands.append(("bsdtar", [fallback_tool, "-xOf", str(archive), "--", member]))
    errors: list[str] = []
    for label, command in commands:
        try:
            extracted = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{label}:{type(exc).__name__}")
            continue
        if extracted.returncode == 0:
            return extracted.stdout, label, ""
        error = extracted.stderr.decode("utf-8", errors="replace").strip()
        errors.append(f"{label}:{error or extracted.returncode}")
    return None, "", "; ".join(errors) or "no extractor succeeded"


def parse_7z_slt(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in str(text or "").splitlines():
        if not line.strip():
            if current.get("Path"):
                records.append(current)
            current = {}
            continue
        if " = " not in line:
            continue
        key, value = line.split(" = ", 1)
        current[key.strip()] = value.strip()
    if current.get("Path"):
        records.append(current)
    return records


def integer_field(value: Any) -> int:
    try:
        return max(0, int(str(value or "0").strip()))
    except ValueError:
        return 0


def unsafe_external_archive_member_reason(
    record: dict[str, str],
    extract_root: Path,
    limits: dict[str, int | float],
    current_total: int,
) -> str:
    raw_name = str(record.get("Path") or "")
    name = PurePosixPath(raw_name)
    if (
        name.is_absolute()
        or "\\" in raw_name
        or "\x00" in raw_name
        or len(raw_name) > 4096
        or not name.parts
        or ":" in name.parts[0]
        or any(len(part.encode("utf-8")) > 255 for part in name.parts)
        or any(part in {"", ".", ".."} for part in name.parts)
    ):
        return "unsafe-path"
    target = extract_root.joinpath(*name.parts).resolve()
    if not path_is_within(target, extract_root.resolve()):
        return "unsafe-path"
    attributes = str(record.get("Attributes") or "").upper()
    if "L" in attributes:
        return "symlink"
    if str(record.get("Encrypted") or "").strip() == "+":
        return "encrypted"
    if Path(raw_name).suffix.lower() in EXECUTABLE_SUFFIXES:
        return "executable-content"
    size = integer_field(record.get("Size"))
    packed_size = integer_field(record.get("Packed Size"))
    if size > int(limits["max_archive_member_bytes"]):
        return "member-too-large"
    if current_total + size > int(limits["max_archive_total_bytes"]):
        return "archive-total-too-large"
    if size / max(1, packed_size) > float(limits["max_archive_ratio"]):
        return "compression-ratio-too-high"
    return ""


def unsafe_zip_member_reason(
    info: zipfile.ZipInfo,
    extract_root: Path,
    limits: dict[str, int | float],
    current_total: int,
) -> str:
    name = PurePosixPath(info.filename)
    if (
        name.is_absolute()
        or "\\" in info.filename
        or "\x00" in info.filename
        or len(info.filename) > 4096
        or not name.parts
        or ":" in name.parts[0]
        or any(len(part.encode("utf-8")) > 255 for part in name.parts)
        or any(part in {"", ".", ".."} for part in name.parts)
    ):
        return "unsafe-path"
    target = extract_root.joinpath(*name.parts).resolve()
    if not path_is_within(target, extract_root.resolve()):
        return "unsafe-path"
    mode = info.external_attr >> 16
    if stat.S_IFMT(mode) == stat.S_IFLNK:
        return "symlink"
    if info.flag_bits & 0x1:
        return "encrypted"
    if Path(info.filename).suffix.lower() in EXECUTABLE_SUFFIXES:
        return "executable-content"
    if info.file_size > int(limits["max_archive_member_bytes"]):
        return "member-too-large"
    if current_total + info.file_size > int(limits["max_archive_total_bytes"]):
        return "archive-total-too-large"
    ratio = info.file_size / max(1, info.compress_size)
    if ratio > float(limits["max_archive_ratio"]):
        return "compression-ratio-too-high"
    return ""


def unsafe_package_member_reason(info: zipfile.ZipInfo, limits: dict[str, int | float]) -> str:
    if info.flag_bits & 0x1:
        return "encrypted"
    if info.file_size > int(limits["max_archive_member_bytes"]):
        return "member-too-large"
    ratio = info.file_size / max(1, info.compress_size)
    if ratio > float(limits["max_archive_ratio"]):
        return "compression-ratio-too-high"
    return ""


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def archive_inventory_text(name: str, members: list[dict[str, Any]], readable: list[dict[str, Any]]) -> str:
    lines = [f"# Archive: {name}", "", "## Member inventory"]
    for item in members:
        state = item.get("read_status") or item.get("status") or "listed"
        reason = f" ({item.get('reason')})" if item.get("reason") else ""
        lines.append(f"- {item.get('name')} - {item.get('size_bytes', 0)} bytes - {state}{reason}")
    if readable:
        lines.extend(["", "## Readable member previews"])
        for item in readable:
            lines.extend(
                [
                    "",
                    f"### {item.get('name')}",
                    str(item.get("text_preview") or "(readable text saved separately)"),
                ]
            )
    return "\n".join(lines)


def finalize_result(result: dict[str, Any], output_dir: Path, limits: dict[str, int | float]) -> dict[str, Any]:
    raw_text = str(result.pop("text", "") or "")
    text = bound_text(normalize_text(raw_text), int(limits["max_text_chars"])) if raw_text else ""
    if text:
        text_path = output_dir / "document_content.md"
        text_path.write_text(document_markdown(result, text), encoding="utf-8")
        result["text_path"] = str(text_path)
        result["agent_context_path"] = str(text_path)
        result["character_count"] = len(text)
        result["text_preview"] = compact_preview(text, 1800)
        result["text_truncated"] = len(raw_text) > len(text)
    result["limits"] = limits
    manifest_path = output_dir / "document_read_manifest.json"
    result["manifest_json"] = str(manifest_path)
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def document_markdown(result: dict[str, Any], text: str) -> str:
    lines = [
        "# Extracted Document Content",
        "",
        f"- Source: `{result.get('filename') or ''}`",
        f"- Kind: `{result.get('kind') or ''}`",
        f"- Method: `{result.get('method') or ''}`",
        f"- Status: `{result.get('status') or ''}`",
        "",
        "## Content",
        "",
        text,
        "",
    ]
    return "\n".join(lines)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def bound_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\n[Content truncated at configured safety limit.]"


def compact_preview(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "..."


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return slug[:80] or "document"


def safe_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_limited_bytes(path: Path, limit: int) -> tuple[bytes, bool]:
    with path.open("rb") as handle:
        data = handle.read(max(1, limit) + 1)
    return data[:limit], len(data) > limit


def run_external(command: list[str], *, timeout: int, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, 124, "", f"{type(exc).__name__}: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_document(args.source, args.output_dir)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result.get("text_path") or result.get("manifest_json") or "")
    return 0 if result.get("status") in READABLE_STATUSES else 2


if __name__ == "__main__":
    raise SystemExit(main())
