import sys
import warnings
from dataclasses import dataclass
from typing import Iterable


SUPPORTED_NETBOX_MAJOR_MINOR = (4, 5)
SUPPORTED_PYTHON_MIN = (3, 12)
SUPPORTED_PYTHON_BEST_EFFORT_MAX = (3, 14)
GA_COMBINATIONS = {
    ((4, 5, 0), (3, 12)),
    ((4, 5, 7), (3, 12)),
}


@dataclass(frozen=True)
class CompatibilityAssessment:
    status: str
    message: str


def _parse_release(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in str(value).split("."):
        digits = []
        for char in part:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if not digits:
            break
        parts.append(int("".join(digits)))
    return tuple(parts)


def _release_prefix(release: Iterable[int], width: int) -> tuple[int, ...]:
    values = tuple(release)
    if len(values) >= width:
        return values[:width]
    return values + (0,) * (width - len(values))


def classify_runtime(*, netbox_version: str, python_version: tuple[int, int]) -> CompatibilityAssessment:
    netbox_release = _parse_release(netbox_version)
    netbox_major_minor = _release_prefix(netbox_release, 2)
    netbox_full = _release_prefix(netbox_release, 3)
    python_full = _release_prefix(python_version, 2)

    if netbox_major_minor != SUPPORTED_NETBOX_MAJOR_MINOR:
        return CompatibilityAssessment(
            status="unsupported",
            message=(
                f"Unsupported runtime: NetBox {netbox_version} is outside the supported "
                f"{SUPPORTED_NETBOX_MAJOR_MINOR[0]}.{SUPPORTED_NETBOX_MAJOR_MINOR[1]}.x release line."
            ),
        )

    if python_full < SUPPORTED_PYTHON_MIN or python_full > SUPPORTED_PYTHON_BEST_EFFORT_MAX:
        return CompatibilityAssessment(
            status="unsupported",
            message=(
                f"Unsupported runtime: Python {python_full[0]}.{python_full[1]} is outside the "
                f"documented {SUPPORTED_PYTHON_MIN[0]}.{SUPPORTED_PYTHON_MIN[1]}-"
                f"{SUPPORTED_PYTHON_BEST_EFFORT_MAX[0]}.{SUPPORTED_PYTHON_BEST_EFFORT_MAX[1]} range."
            ),
        )

    if (netbox_full, python_full) in GA_COMBINATIONS:
        return CompatibilityAssessment(
            status="ga",
            message=(
                f"GA runtime: NetBox {netbox_version} with Python "
                f"{python_full[0]}.{python_full[1]} is a verified release-gating combination."
            ),
        )

    if python_full == SUPPORTED_PYTHON_MIN:
        return CompatibilityAssessment(
            status="beta",
            message=(
                f"Beta runtime: NetBox {netbox_version} with Python "
                f"{python_full[0]}.{python_full[1]} is inside the supported 4.5.x line, "
                "but this exact patch combination is not release-gated."
            ),
        )

    return CompatibilityAssessment(
        status="best_effort",
        message=(
            f"Best-effort runtime: NetBox {netbox_version} with Python "
            f"{python_full[0]}.{python_full[1]} is allowed for operator evaluation, "
            "but the combination is not release-gated."
        ),
    )


def emit_runtime_compatibility_warning(*, netbox_version: str, python_version: tuple[int, int] | None = None) -> CompatibilityAssessment:
    assessment = classify_runtime(
        netbox_version=netbox_version,
        python_version=_release_prefix(python_version or sys.version_info[:2], 2),
    )
    if assessment.status != "ga":
        warnings.warn(assessment.message, RuntimeWarning, stacklevel=2)
    return assessment
