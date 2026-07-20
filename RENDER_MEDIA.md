# Render media files

Uploaded images must not be stored inside the project directory on Render, because
that filesystem is recreated on deploys and restarts.

Use a Render persistent disk and set these environment variables:

```text
DJANGO_MEDIA_ROOT=/var/data/media
DJANGO_SERVE_MEDIA_FILES=true
DJANGO_DEBUG=false
```

Mount the persistent disk at:

```text
/var/data
```

After that, new uploaded files such as store logos, product images, payment icons,
and payment proof images will be saved under `/var/data/media` and will survive
service restarts and deploys.

Existing database rows may still point to files that were already deleted from
the old temporary path. Those images need to be uploaded again unless they were
backed up before the Render restart/deploy.
