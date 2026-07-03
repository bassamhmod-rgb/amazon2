from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS "dashboard_expensereason" (
                    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                    "name" varchar(120) NOT NULL,
                    "store_id" bigint NOT NULL REFERENCES "stores_store" ("id") DEFERRABLE INITIALLY DEFERRED
                );
                CREATE TABLE IF NOT EXISTS "dashboard_expensetype" (
                    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                    "name" varchar(120) NOT NULL,
                    "store_id" bigint NOT NULL REFERENCES "stores_store" ("id") DEFERRABLE INITIALLY DEFERRED
                );
                CREATE TABLE IF NOT EXISTS "dashboard_expense" (
                    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                    "amount" decimal NOT NULL,
                    "date" date NOT NULL,
                    "notes" text NOT NULL,
                    "expense_reason_id" bigint NULL REFERENCES "dashboard_expensereason" ("id") DEFERRABLE INITIALLY DEFERRED,
                    "expense_type_id" bigint NULL REFERENCES "dashboard_expensetype" ("id") DEFERRABLE INITIALLY DEFERRED,
                    "store_id" bigint NOT NULL REFERENCES "stores_store" ("id") DEFERRABLE INITIALLY DEFERRED
                );
                CREATE INDEX IF NOT EXISTS "dashboard_expensereason_store_id_0536e53c" ON "dashboard_expensereason" ("store_id");
                CREATE INDEX IF NOT EXISTS "dashboard_expensetype_store_id_7e6e0d6a" ON "dashboard_expensetype" ("store_id");
                CREATE INDEX IF NOT EXISTS "dashboard_expense_expense_reason_id_fdb1431a" ON "dashboard_expense" ("expense_reason_id");
                CREATE INDEX IF NOT EXISTS "dashboard_expense_expense_type_id_dbafa141" ON "dashboard_expense" ("expense_type_id");
                CREATE INDEX IF NOT EXISTS "dashboard_expense_store_id_35055ccb" ON "dashboard_expense" ("store_id");
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
