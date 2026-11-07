"""
Standalone script to drop users_loginotp table from PostgreSQL
and synchronize django_migrations table to reflect re-sequenced migrations.

Usage:
    & "backend/env/Scripts/python.exe" backend/drop_loginotp_table.py
"""

import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

# Configure Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

try:
    import django
    django.setup()
    from django.db import connection
except Exception as e:
    print(f"Error initializing Django: {e}")
    sys.exit(1)


def cleanup_loginotp():
    print("Connecting to database...")
    try:
        with connection.cursor() as cursor:
            # 1. Drop the table if it exists
            print("Executing: DROP TABLE IF EXISTS users_loginotp CASCADE;")
            cursor.execute("DROP TABLE IF EXISTS users_loginotp CASCADE;")
            print("✓ Dropped table users_loginotp (if it existed).")

            # 2. Clean up django_migrations table
            print("Checking django_migrations records...")
            cursor.execute(
                "SELECT name FROM django_migrations WHERE app = 'users' ORDER BY id;"
            )
            existing_migrations = [row[0] for row in cursor.fetchall()]
            print(f"Current users migrations in DB: {existing_migrations}")

            # Delete 0005_loginotp
            cursor.execute(
                "DELETE FROM django_migrations WHERE app = 'users' AND name = '0005_loginotp';"
            )
            deleted_count = cursor.rowcount
            if deleted_count:
                print(f"✓ Removed '0005_loginotp' entry from django_migrations.")

            # Update 0006_profile -> 0005_profile
            cursor.execute(
                "UPDATE django_migrations SET name = '0005_profile' WHERE app = 'users' AND name = '0006_profile';"
            )
            if cursor.rowcount:
                print(f"✓ Renamed '0006_profile' -> '0005_profile' in django_migrations.")

            # Update 0007_emailchangeotp -> 0006_emailchangeotp
            cursor.execute(
                "UPDATE django_migrations SET name = '0006_emailchangeotp' WHERE app = 'users' AND name = '0007_emailchangeotp';"
            )
            if cursor.rowcount:
                print(f"✓ Renamed '0007_emailchangeotp' -> '0006_emailchangeotp' in django_migrations.")

            # Query updated migrations
            cursor.execute(
                "SELECT name FROM django_migrations WHERE app = 'users' ORDER BY id;"
            )
            updated_migrations = [row[0] for row in cursor.fetchall()]
            print(f"Updated users migrations in DB: {updated_migrations}")

            print("\nDatabase cleanup completed successfully!")

    except Exception as e:
        print(f"Database operation error (is PostgreSQL running?): {e}")
        print("\nIf PostgreSQL is offline, you can run this script later or run SQL manually:")
        print("    DROP TABLE IF EXISTS users_loginotp CASCADE;")
        print("    DELETE FROM django_migrations WHERE app = 'users' AND name = '0005_loginotp';")
        print("    UPDATE django_migrations SET name = '0005_profile' WHERE app = 'users' AND name = '0006_profile';")
        print("    UPDATE django_migrations SET name = '0006_emailchangeotp' WHERE app = 'users' AND name = '0007_emailchangeotp';")


if __name__ == "__main__":
    cleanup_loginotp()

