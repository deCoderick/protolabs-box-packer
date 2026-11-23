from collections import Counter
from collections.abc import Sequence
from http import HTTPStatus
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request

from box_packer.api.errors import ApiError
from box_packer.api.schemas import ErrorDetail, ErrorResponse, PackageIn, PackingResponse
from box_packer.catalogue import Catalogue
from box_packer.solver import UnpackablePackagesError, UnpackableReason, pack

# Packing time grows roughly quadratically; this keeps a single request bounded.
MAX_PACKAGES_PER_REQUEST = 1000

SPEC_EXAMPLE = [
    {"id": 123, "width": 10, "height": 10, "length": 10, "weight": 5},
    {"id": 125, "width": 5, "height": 5, "length": 10, "weight": 10},
]

_UNPACKABLE_MESSAGES = {
    UnpackableReason.TOO_LARGE: "is larger than every box, in any orientation",
    UnpackableReason.TOO_HEAVY: "exceeds every box's weight limit",
    UnpackableReason.TOO_LARGE_AND_TOO_HEAVY: (
        "is larger than every box and exceeds every box's weight limit"
    ),
    UnpackableReason.NO_BOX_FITS_SIZE_AND_WEIGHT: (
        "fits some box by size and another by weight, but no single box by both"
    ),
}

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    HTTPStatus.BAD_REQUEST: {"model": ErrorResponse, "description": "Malformed JSON."},
    HTTPStatus.UNPROCESSABLE_ENTITY: {
        "model": ErrorResponse,
        "description": "Invalid packages, duplicate ids, or packages that fit in no box.",
    },
}

router = APIRouter()


def get_catalogue(request: Request) -> Catalogue:
    catalogue: Catalogue = request.app.state.catalogue
    return catalogue


@router.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/packing",
    tags=["packing"],
    summary="Compute the shipping boxes needed for a list of packages",
    responses=_ERROR_RESPONSES,
)
def create_packing(
    packages: Annotated[
        list[PackageIn],
        Body(max_length=MAX_PACKAGES_PER_REQUEST, examples=[SPEC_EXAMPLE]),
    ],
    catalogue: Annotated[Catalogue, Depends(get_catalogue)],
) -> PackingResponse:
    if duplicates := _duplicate_id_details(packages):
        raise ApiError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "duplicate_package_ids",
            "Package ids must be unique.",
            duplicates,
        )
    try:
        boxes = pack([p.to_domain() for p in packages], catalogue)
    except UnpackablePackagesError as exc:
        raise _unpackable_error(exc, packages) from exc
    return PackingResponse.from_domain(boxes)


def _duplicate_id_details(packages: Sequence[PackageIn]) -> list[ErrorDetail]:
    counts = Counter(p.id for p in packages)
    return [
        ErrorDetail(
            loc=[index, "id"],
            package_id=package.id,
            type="duplicate_id",
            message=f"Package id {package.id} appears {counts[package.id]} times.",
        )
        for index, package in enumerate(packages)
        if counts[package.id] > 1
    ]


def _unpackable_error(exc: UnpackablePackagesError, packages: Sequence[PackageIn]) -> ApiError:
    index_by_id = {p.id: index for index, p in enumerate(packages)}
    details = [
        ErrorDetail(
            loc=[index_by_id[item.package_id]],
            package_id=item.package_id,
            type=item.reason,
            message=f"Package {item.package_id} {_UNPACKABLE_MESSAGES[item.reason]}.",
        )
        for item in exc.packages
    ]
    return ApiError(
        HTTPStatus.UNPROCESSABLE_ENTITY,
        "unpackable_packages",
        "Some packages do not fit in any available box.",
        details,
    )
