# Render media files

Uploaded images must not be stored inside the project directory on Render, because
that filesystem is recreated on deploys and restarts.

## Free Render instance

Free Render instances do not support persistent disks. Use Cloudinary instead.

Set this environment variable in Render:

```text
CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME
```

Also keep:

```text
DJANGO_DEBUG=false
```

Do not set `DJANGO_MEDIA_ROOT=/var/data/media` unless the service has a Render
persistent disk mounted at `/var/data`.

## Paid Render instance with disk

If the service has a persistent disk, mount it at:

```text
/var/data
```

Then set:

```text
DJANGO_MEDIA_ROOT=/var/data/media
DJANGO_SERVE_MEDIA_FILES=true
DJANGO_DEBUG=false
```

Existing database rows may still point to files that were already deleted from
the old temporary path. Those images need to be uploaded again unless they were
backed up before the Render restart/deploy.
