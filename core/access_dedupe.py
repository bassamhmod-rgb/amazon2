from __future__ import annotations

from typing import Any, Tuple

from django.db.models import Count, Min, QuerySet


def dedupe_keep_oldest_for_value(
    qs: QuerySet,
    *,
    field_name: str,
    value: Any,
    pk_name: str = "id",
) -> Tuple[int, int | None]:
    """
    Delete duplicates in `qs` where `field_name == value`, keeping the oldest row.

    Oldest is defined as the smallest primary key (`pk_name`), which matches the
    common meaning of "السجل القديم" in this project.

    Returns (deleted_count, kept_id). If `value` is empty/None/0 or no rows exist,
    returns (0, None).
    """
    if value in (None, "", 0):
        return 0, None

    try:
        normalized_value = int(value)
    except (TypeError, ValueError):
        return 0, None

    if normalized_value == 0:
        return 0, None

    keep_id = (
        qs.filter(**{field_name: normalized_value})
        .order_by(pk_name)
        .values_list(pk_name, flat=True)
        .first()
    )
    if not keep_id:
        return 0, None

    deleted_count, _ = (
        qs.filter(**{field_name: normalized_value}).exclude(**{pk_name: keep_id}).delete()
    )
    return deleted_count, int(keep_id)


def dedupe_keep_oldest(
    qs: QuerySet,
    *,
    field_name: str,
    pk_name: str = "id",
) -> int:
    """
    Delete duplicates in `qs` by `field_name`, keeping the oldest row per value.

    Skips rows where field is NULL or 0.
    Returns total deleted rows count.
    """
    field_isnull = f"{field_name}__isnull"
    duplicates = (
        qs.exclude(**{field_isnull: True})
        .exclude(**{field_name: 0})
        .values(field_name)
        .annotate(count=Count(pk_name), keep_id=Min(pk_name))
        .filter(count__gt=1)
    )

    duplicate_values = list(duplicates.values_list(field_name, flat=True))
    if not duplicate_values:
        return 0

    keep_ids = list(duplicates.values_list("keep_id", flat=True))
    deleted_count, _ = (
        qs.filter(**{f"{field_name}__in": duplicate_values})
        .exclude(**{f"{pk_name}__in": keep_ids})
        .delete()
    )
    return deleted_count

