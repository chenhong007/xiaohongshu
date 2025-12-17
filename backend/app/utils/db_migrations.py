"""
Database Migrations Utility

Provides utility functions for database schema migrations.
These are run automatically on application startup to ensure
the database schema is up to date.
"""
from sqlalchemy import inspect, text
from ..extensions import db
from ..utils.logger import get_logger

logger = get_logger('db_migrations')


def run_migrations():
    """Run all pending migrations.
    
    This function is called on application startup to ensure
    the database schema is up to date.
    """
    try:
        _add_account_health_status_fields()
    except Exception as e:
        logger.error(f"Migration failed: {e}")


def _add_account_health_status_fields():
    """Add health status fields to accounts table if they don't exist.
    
    Fields added:
    - health_status: Current health status (healthy, cookie_expired, rate_limited, etc.)
    - health_message: Detailed message about the health status
    - health_updated_at: When the health status was last updated
    """
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('accounts')]
    
    migrations_needed = []
    
    if 'health_status' not in columns:
        migrations_needed.append(
            "ALTER TABLE accounts ADD COLUMN health_status VARCHAR(32) DEFAULT 'healthy'"
        )
    
    if 'health_message' not in columns:
        migrations_needed.append(
            "ALTER TABLE accounts ADD COLUMN health_message TEXT"
        )
    
    if 'health_updated_at' not in columns:
        migrations_needed.append(
            "ALTER TABLE accounts ADD COLUMN health_updated_at TIMESTAMP"
        )
    
    if migrations_needed:
        logger.info(f"Running {len(migrations_needed)} account health status migrations...")
        for sql in migrations_needed:
            try:
                db.session.execute(text(sql))
                logger.info(f"Migration executed: {sql[:50]}...")
            except Exception as e:
                logger.warning(f"Migration may have already been applied: {e}")
        db.session.commit()
        logger.info("Account health status migrations completed")
    else:
        logger.debug("Account health status fields already exist, no migration needed")


