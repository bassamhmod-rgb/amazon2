"""Content receipts for overlapping, minute-resolution incremental pulls.

Snapshot expiry always replays data; only the client can acknowledge a snapshot after
it commits the returned rows. Tokens are scoped to a store and resource.
"""
import hashlib
import json
from datetime import timedelta

from django.utils import timezone
from rest_framework.utils.encoders import JSONEncoder

from .models import PullSnapshot


def changed_rows(request, resource, merchant_id, rows):
    token = request.query_params.get("snapshot_token", "")
    now = timezone.now()
    snapshot = PullSnapshot.objects.filter(
        token=token, resource=resource, merchant_id=merchant_id, expires_at__gt=now,
    ).first() if token else None
    previous = snapshot.fingerprints if snapshot else {}
    current = dict(previous)
    changed = []
    for row in rows:
        identity = str(row["id"])
        digest = hashlib.sha256(json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            cls=JSONEncoder,
        ).encode()).hexdigest()
        if previous.get(identity) != digest:
            changed.append(row)
        current[identity] = digest
    new_token = hashlib.sha256(json.dumps(
        [resource, merchant_id, current], sort_keys=True,
    ).encode()).hexdigest()
    PullSnapshot.objects.update_or_create(token=new_token, defaults={
        "merchant_id": merchant_id, "resource": resource,
        "fingerprints": current, "expires_at": now + timedelta(days=7),
    })
    PullSnapshot.objects.filter(expires_at__lte=now).delete()
    return changed, new_token
