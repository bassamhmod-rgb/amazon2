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

                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'accounts_appupdate'
                      AND column_name = 'prices_version'
                      AND data_type = 'date'
                ) THEN
                    ALTER TABLE accounts_appupdate
                    ALTER COLUMN prices_version TYPE integer
                    USING 0;
                END IF;
            END $$;
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0019_fix_appupdate_version_type"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
