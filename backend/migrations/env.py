from alembic import context

from app.db import Base, engine
from app import models  # Register the two tables with Base.metadata.

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
