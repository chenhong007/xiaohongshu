"""
Flask Extensions Initialization

This module initializes Flask extensions that are shared across the application.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Database instance
db = SQLAlchemy()

# Flask-Migrate instance
migrate = Migrate()
