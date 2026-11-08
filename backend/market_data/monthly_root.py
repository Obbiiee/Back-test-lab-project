"""Pinned root validation shared by local and object-store Monthly Parquet readers."""

import ipaddress
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
from urllib.parse import urlsplit

from contracts.primitives import require


_BUCKET = re.compile(r"[a-z0-9](?:[a-z0-9.-]{1,61}[a-z0-9])?\Z")
_SEGMENT = re.compile(r"[A-Za-z0-9._=-]+\Z")


def parse_s3_monthly_root(value):
    """Return canonical ``(uri, bucket, prefix)`` for a safe S3 root."""
    require(type(value) is str and len(value) <= 4096, "root", "REFUSED_SOURCE")
    parsed = urlsplit(value)
    bucket = parsed.netloc
    raw_path = parsed.path[:-1] if parsed.path.endswith("/") else parsed.path
    segments = raw_path[1:].split("/") if raw_path.startswith("/") else []
    try:
        port = parsed.port
    except ValueError:
        require(False, "root", "REFUSED_SOURCE")
        port = None
    require(parsed.scheme == "s3" and bucket == bucket.lower() and
            _BUCKET.fullmatch(bucket) is not None and ".." not in bucket and
            parsed.username is None and parsed.password is None and port is None and
            parsed.query == "" and parsed.fragment == "" and
            raw_path.startswith("/") and len(segments) > 0 and
            all(_SEGMENT.fullmatch(part) is not None and part not in (".", "..")
                for part in segments), "root", "REFUSED_SOURCE")
    try:
        ipaddress.ip_address(bucket)
    except ValueError:
        pass
    else:
        require(False, "root", "REFUSED_SOURCE")
    prefix = "/".join(segments).rstrip("/")
    require(prefix != "", "root", "REFUSED_SOURCE")
    return f"s3://{bucket}/{prefix}", bucket, prefix


def pin_monthly_root(value):
    """Canonicalize an operator-configured local path or S3 URI."""
    require(type(value) is str and len(value) <= 4096, "root", "REFUSED_SOURCE")
    if value.startswith("s3://"):
        return parse_s3_monthly_root(value)[0]
    require(os.path.isabs(value), "root", "REFUSED_SOURCE")
    return os.path.realpath(value)


def monthly_root_from_environment(values):
    """Validate the worker's all-or-nothing synthetic source pin."""
    require(type(values) in (tuple, list) and len(values) == 5,
            "syntheticMonthly", "REFUSED_SOURCE")
    if not any(values):
        require(values[0] is None, "syntheticMonthly", "REFUSED_SOURCE")
        return None
    require(values[0] == "1" and all(values[1:]),
            "syntheticMonthly", "REFUSED_SOURCE")
    root = values[1]
    require(type(root) is str and len(root) <= 4096,
            "syntheticMonthlyRoot", "REFUSED_SOURCE")
    if root.startswith("s3://"):
        return pin_monthly_root(root)
    require(os.path.isabs(root), "syntheticMonthlyRoot", "REFUSED_SOURCE")
    return root


def monthly_object_path(root, base_path, relative):
    """Resolve a manifest child without permitting local or object-store escape."""
    require(type(relative) is str and relative and "\\" not in relative and
            not relative.startswith("/"), "objectPath", "REFUSED_SOURCE")
    parts = relative.split("/")
    require(all(_SEGMENT.fullmatch(part) is not None and part not in (".", "..")
                for part in parts), "objectPath", "REFUSED_SOURCE")
    if isinstance(root, Path):
        target = root.joinpath(*parts)
        resolved = target.resolve()
        require(resolved == target and resolved.is_relative_to(root), "file", "MISSING_CHILD")
        return str(resolved)
    require(type(root) is str and type(base_path) is str, "root", "REFUSED_SOURCE")
    return posixpath.join(base_path, *PurePosixPath(relative).parts)
