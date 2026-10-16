"""Stable installer names and integrity metadata for in-app downloads."""
import hashlib

from django.core.cache import cache
from django.http import HttpResponseRedirect


def file_metadata(field, revision=""):
    if not field:
        return {}
    size = field.storage.size(field.name)
    try:
        modified = field.storage.get_modified_time(field.name).isoformat()
    except (AttributeError, NotImplementedError):
        modified = str(revision)
    identity = f"{field.name}:{size}:{modified}:{revision}"
    key = "app-update-digest:" + hashlib.sha256(identity.encode()).hexdigest()
    digest = cache.get(key)
    if not digest:
        checksum = hashlib.sha256()
        with field.storage.open(field.name, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                checksum.update(chunk)
        digest = checksum.hexdigest()
        cache.set(key, digest, 86400)
    return {"file_size": size, "sha256": digest}


def installer_response(field, platform, release):
    extension = "apk" if platform == "android" else "exe"
    # Keep large/slow downloads on the existing media server (Nginx or storage)
    # instead of occupying a Django worker for the entire transfer. The app
    # follows this redirect internally and owns the stable local filename.
    response = HttpResponseRedirect(field.url)
    response["Content-Disposition"] = f'attachment; filename="alaman_pos_update_{release}.{extension}"'
    response["Cache-Control"] = "private, no-cache"
    return response
