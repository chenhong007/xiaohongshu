#!/usr/bin/env python3
"""
SQLite to PostgreSQL Data Migration Script

This script migrates data from SQLite database to PostgreSQL.
Supports batch migration with progress tracking and data verification.

Usage:
    python migrate_sqlite_to_pg.py --sqlite-path /path/to/xhs_data.db --pg-url postgresql://user:pass@host:5432/db

Environment variables can also be used:
    SQLITE_PATH: Path to SQLite database file
    PG_DATABASE_URL: PostgreSQL connection URL
"""
import os
import sys
import argparse
import time
from datetime import datetime

try:
    from sqlalchemy import create_engine, text, inspect
    from sqlalchemy.orm import sessionmaker
except ImportError:
    print("Error: SQLAlchemy is required. Install with: pip install sqlalchemy")
    sys.exit(1)

# Batch size for migration
BATCH_SIZE = 1000


def get_sqlite_engine(sqlite_path):
    """Create SQLite engine"""
    if not os.path.exists(sqlite_path):
        print(f"Error: SQLite database not found: {sqlite_path}")
        sys.exit(1)
    
    return create_engine(
        f'sqlite:///{sqlite_path}',
        connect_args={'check_same_thread': False}
    )


def get_pg_engine(pg_url):
    """Create PostgreSQL engine"""
    return create_engine(
        pg_url,
        pool_size=10,
        pool_recycle=300,
        pool_pre_ping=True
    )


def wait_for_postgres(engine, max_retries=30, retry_interval=2):
    """Wait for PostgreSQL to be ready"""
    print("Waiting for PostgreSQL to be ready...")
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("PostgreSQL is ready!")
            return True
        except Exception as e:
            if i < max_retries - 1:
                print(f"  Attempt {i + 1}/{max_retries}: Connection failed, retrying in {retry_interval}s...")
                time.sleep(retry_interval)
            else:
                print(f"Error: Could not connect to PostgreSQL after {max_retries} attempts")
                print(f"  Last error: {e}")
                return False
    return False


def get_table_columns(engine, table_name):
    """Get column names for a table"""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return [col['name'] for col in columns]


def get_row_count(engine, table_name):
    """Get row count for a table"""
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return result.scalar()


def create_pg_tables(pg_engine):
    """Create tables in PostgreSQL using raw DDL"""
    print("\nCreating PostgreSQL tables...")
    
    # Create tables using raw DDL - no app dependencies needed
    with pg_engine.connect() as conn:
        # Create accounts table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(64) UNIQUE NOT NULL,
                name VARCHAR(128),
                avatar VARCHAR(512),
                red_id VARCHAR(64),
                "desc" TEXT,
                fans INTEGER DEFAULT 0,
                follows INTEGER DEFAULT 0,
                interaction INTEGER DEFAULT 0,
                last_sync TIMESTAMP,
                total_msgs INTEGER DEFAULT 0,
                loaded_msgs INTEGER DEFAULT 0,
                progress INTEGER DEFAULT 0,
                status VARCHAR(32) DEFAULT 'pending',
                error_message TEXT,
                sync_heartbeat TIMESTAMP,
                sync_logs TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Create index on user_id
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_accounts_user_id ON accounts(user_id)
        """))
        
        # Create notes table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS notes (
                note_id VARCHAR(64) PRIMARY KEY,
                user_id VARCHAR(64) REFERENCES accounts(user_id),
                nickname VARCHAR(128),
                avatar VARCHAR(512),
                title VARCHAR(256),
                "desc" TEXT,
                type VARCHAR(32),
                liked_count INTEGER DEFAULT 0,
                collected_count INTEGER DEFAULT 0,
                comment_count INTEGER DEFAULT 0,
                share_count INTEGER DEFAULT 0,
                upload_time VARCHAR(64),
                video_addr VARCHAR(512),
                image_list TEXT,
                tags TEXT,
                ip_location VARCHAR(64),
                cover_remote VARCHAR(512),
                cover_local VARCHAR(512),
                xsec_token VARCHAR(256),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Create indexes on notes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_notes_user_id ON notes(user_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_notes_type ON notes(type)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_notes_upload_time ON notes(upload_time)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_notes_user_upload_time ON notes(user_id, upload_time)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_notes_user_type ON notes(user_id, type)
        """))
        
        # Create cookies table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cookies (
                id SERIAL PRIMARY KEY,
                cookie_str TEXT,
                encrypted_cookie TEXT,
                user_id VARCHAR(64),
                nickname VARCHAR(128),
                avatar VARCHAR(512),
                is_active BOOLEAN DEFAULT TRUE,
                is_valid BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                run_start_time TIMESTAMP,
                total_run_seconds INTEGER DEFAULT 0,
                last_valid_duration INTEGER DEFAULT 0,
                invalidated_at TIMESTAMP
            )
        """))
        
        conn.commit()
    
    print("  Tables created successfully!")


def migrate_table(sqlite_engine, pg_engine, table_name, batch_size=BATCH_SIZE):
    """Migrate a single table from SQLite to PostgreSQL"""
    print(f"\n  Migrating table: {table_name}")
    
    # Get source row count
    source_count = get_row_count(sqlite_engine, table_name)
    print(f"    Source rows: {source_count}")
    
    if source_count == 0:
        print(f"    No data to migrate")
        return 0, 0
    
    # Get columns from SQLite
    sqlite_columns = get_table_columns(sqlite_engine, table_name)
    
    # Get columns from PostgreSQL
    pg_columns = get_table_columns(pg_engine, table_name)
    
    # Find common columns
    common_columns = [c for c in sqlite_columns if c in pg_columns]
    columns_str = ', '.join([f'"{c}"' for c in common_columns])
    placeholders = ', '.join([f':{c}' for c in common_columns])
    
    print(f"    Migrating columns: {len(common_columns)}")
    
    # Determine primary key for conflict resolution
    pk_column = 'id' if 'id' in common_columns else common_columns[0]
    if table_name == 'notes':
        pk_column = 'note_id'
    
    # Build upsert query for PostgreSQL
    update_cols = ', '.join([f'"{c}" = EXCLUDED."{c}"' for c in common_columns if c != pk_column])
    
    if update_cols:
        upsert_query = f"""
            INSERT INTO {table_name} ({columns_str})
            VALUES ({placeholders})
            ON CONFLICT ("{pk_column}") DO UPDATE SET {update_cols}
        """
    else:
        upsert_query = f"""
            INSERT INTO {table_name} ({columns_str})
            VALUES ({placeholders})
            ON CONFLICT ("{pk_column}") DO NOTHING
        """
    
    # Migrate in batches
    migrated = 0
    offset = 0
    
    while offset < source_count:
        # Read batch from SQLite
        with sqlite_engine.connect() as sqlite_conn:
            result = sqlite_conn.execute(
                text(f"SELECT {columns_str} FROM {table_name} LIMIT {batch_size} OFFSET {offset}")
            )
            rows = result.fetchall()
        
        if not rows:
            break
        
        # Convert rows to dicts
        batch_data = []
        # Boolean columns that need conversion from SQLite integer to PostgreSQL boolean
        boolean_columns = {'is_active', 'is_valid'}
        
        for row in rows:
            row_dict = {}
            for i, col in enumerate(common_columns):
                value = row[i]
                # Handle datetime conversion
                if isinstance(value, str) and 'T' in value and value.endswith('Z'):
                    try:
                        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except ValueError:
                        pass
                # Handle boolean conversion (SQLite stores as 0/1 integer)
                if col in boolean_columns and isinstance(value, int):
                    value = bool(value)
                row_dict[col] = value
            batch_data.append(row_dict)
        
        # Insert batch into PostgreSQL
        with pg_engine.connect() as pg_conn:
            try:
                # Try batch insert first
                for row_dict in batch_data:
                    pg_conn.execute(text(upsert_query), row_dict)
                pg_conn.commit()
            except Exception:
                # If batch fails, rollback and try row by row
                pg_conn.rollback()
                for row_dict in batch_data:
                    try:
                        with pg_engine.connect() as single_conn:
                            single_conn.execute(text(upsert_query), row_dict)
                            single_conn.commit()
                    except Exception as e:
                        print(f"    Warning: Failed to insert row: {e}")
                        continue
        
        migrated += len(rows)
        offset += batch_size
        
        # Progress update
        progress = min(100, int(migrated / source_count * 100))
        print(f"    Progress: {migrated}/{source_count} ({progress}%)", end='\r')
    
    print(f"    Progress: {migrated}/{source_count} (100%)    ")
    
    # Verify migration
    dest_count = get_row_count(pg_engine, table_name)
    print(f"    Destination rows: {dest_count}")
    
    return source_count, dest_count


def verify_migration(sqlite_engine, pg_engine, tables):
    """Verify data integrity after migration"""
    print("\n" + "=" * 50)
    print("Data Verification")
    print("=" * 50)
    
    all_passed = True
    
    for table in tables:
        source_count = get_row_count(sqlite_engine, table)
        dest_count = get_row_count(pg_engine, table)
        
        status = "✓" if source_count == dest_count else "✗"
        if source_count != dest_count:
            all_passed = False
        
        print(f"  {status} {table}: SQLite={source_count}, PostgreSQL={dest_count}")
    
    return all_passed


def reset_sequences(pg_engine, tables_with_serial):
    """Reset PostgreSQL sequences to continue from max id"""
    print("\nResetting PostgreSQL sequences...")
    
    for table, id_col in tables_with_serial:
        try:
            with pg_engine.connect() as conn:
                # Get max id
                result = conn.execute(text(f'SELECT MAX("{id_col}") FROM {table}'))
                max_id = result.scalar() or 0
                
                # Reset sequence
                seq_name = f"{table}_{id_col}_seq"
                conn.execute(text(f"SELECT setval('{seq_name}', {max_id + 1}, false)"))
                conn.commit()
                
            print(f"  {table}.{id_col}: sequence set to {max_id + 1}")
        except Exception as e:
            print(f"  Warning: Could not reset sequence for {table}: {e}")


def main():
    parser = argparse.ArgumentParser(description='Migrate SQLite to PostgreSQL')
    parser.add_argument('--sqlite-path', 
                        default=os.environ.get('SQLITE_PATH', '/app/xhs_data.db'),
                        help='Path to SQLite database')
    parser.add_argument('--pg-url',
                        default=os.environ.get('PG_DATABASE_URL', 
                                               'postgresql://xhs:xhs_secret_2024@postgres:5432/xhs_data'),
                        help='PostgreSQL connection URL')
    parser.add_argument('--batch-size', type=int, default=BATCH_SIZE,
                        help=f'Batch size for migration (default: {BATCH_SIZE})')
    parser.add_argument('--skip-verify', action='store_true',
                        help='Skip data verification after migration')
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("SQLite to PostgreSQL Migration")
    print("=" * 50)
    print(f"SQLite Path: {args.sqlite_path}")
    print(f"PostgreSQL URL: {args.pg_url.replace(args.pg_url.split(':')[2].split('@')[0], '***')}")
    print(f"Batch Size: {args.batch_size}")
    
    # Create engines
    sqlite_engine = get_sqlite_engine(args.sqlite_path)
    pg_engine = get_pg_engine(args.pg_url)
    
    # Wait for PostgreSQL
    if not wait_for_postgres(pg_engine):
        sys.exit(1)
    
    # Create tables
    create_pg_tables(pg_engine)
    
    # Define tables to migrate in order (respecting foreign keys)
    tables = ['accounts', 'notes', 'cookies']
    
    # Migrate each table
    print("\n" + "=" * 50)
    print("Starting Migration")
    print("=" * 50)
    
    start_time = time.time()
    results = {}
    
    for table in tables:
        try:
            source, dest = migrate_table(sqlite_engine, pg_engine, table, args.batch_size)
            results[table] = {'source': source, 'dest': dest}
        except Exception as e:
            print(f"\n  Error migrating {table}: {e}")
            results[table] = {'source': 0, 'dest': 0, 'error': str(e)}
    
    elapsed = time.time() - start_time
    
    # Reset sequences for tables with SERIAL primary keys
    reset_sequences(pg_engine, [('accounts', 'id'), ('cookies', 'id')])
    
    # Verify if not skipped
    if not args.skip_verify:
        all_passed = verify_migration(sqlite_engine, pg_engine, tables)
    else:
        all_passed = True
        print("\nVerification skipped")
    
    # Summary
    print("\n" + "=" * 50)
    print("Migration Summary")
    print("=" * 50)
    print(f"Total time: {elapsed:.2f} seconds")
    
    total_source = sum(r.get('source', 0) for r in results.values())
    total_dest = sum(r.get('dest', 0) for r in results.values())
    print(f"Total rows migrated: {total_dest}/{total_source}")
    
    if all_passed:
        print("\n✓ Migration completed successfully!")
        return 0
    else:
        print("\n✗ Migration completed with warnings. Please verify data integrity.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
