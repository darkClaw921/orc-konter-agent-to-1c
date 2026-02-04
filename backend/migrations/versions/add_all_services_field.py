"""add all_services field

Revision ID: add_all_services_field
Revises: add_services_field
Create Date: 2026-02-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_all_services_field'
down_revision = 'add_services_field'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поле all_services в таблицу contract_data
    op.add_column('contract_data', sa.Column('all_services', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    # Удаляем поле all_services из таблицы contract_data
    op.drop_column('contract_data', 'all_services')
