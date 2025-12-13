#!/usr/bin/env python
"""
Database Management Script

This script provides CLI commands for database management using Flask-Migrate.

Usage:
    # Initialize migrations (first time only)
    python manage.py db init
    
    # Create a new migration
    python manage.py db migrate -m "Add new column"
    
    # Apply migrations
    python manage.py db upgrade
    
    # Rollback migration
    python manage.py db downgrade
    
    # Show migration history
    python manage.py db history
"""
import os
import sys

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask.cli import with_appcontext
import click

from app import create_app
from app.extensions import db

# Create app instance
app = create_app()


@app.cli.command('db-status')
@with_appcontext
def db_status():
    """Show database connection status and table info."""
    try:
        # Test connection
        result = db.session.execute(db.text('SELECT 1'))
        result.fetchone()
        click.echo(click.style('✓ Database connection OK', fg='green'))
        
        # Get table info from PostgreSQL
        tables = db.session.execute(
            db.text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        ).fetchall()
        
        click.echo(f'\nTables in database:')
        for table in tables:
            click.echo(f'  - {table[0]}')
            
    except Exception as e:
        click.echo(click.style(f'✗ Database error: {e}', fg='red'))


@app.cli.command('cleanup-stale')
@with_appcontext
def cleanup_stale():
    """Clean up stale sync tasks."""
    from app.services.sync_service import SyncService
    cleaned = SyncService.cleanup_stale_tasks()
    if cleaned > 0:
        click.echo(click.style(f'✓ Cleaned {cleaned} stale tasks', fg='green'))
    else:
        click.echo('No stale tasks found')


if __name__ == '__main__':
    # Support running with flask CLI
    import subprocess
    
    if len(sys.argv) > 1 and sys.argv[1] == 'db':
        # Use flask db commands
        os.environ['FLASK_APP'] = 'manage.py'
        subprocess.run(['flask'] + sys.argv[1:])
    else:
        # Run custom commands
        app.cli()
