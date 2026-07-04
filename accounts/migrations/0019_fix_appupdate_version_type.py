from django.db import migrations


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'accounts_appupdate'
                      AND column_name = 'version'
                      AND data_type = 'date'
                ) THEN
                    ALTER TABLE accounts_appupdate
                    ALTER COLUMN version TYPE integer
                    USING 0;
                END IF;
            END $$;
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_storeuser_auth_user"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
