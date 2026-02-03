"""add services field

Revision ID: add_services_field
Revises: add_customer_contractor
Create Date: 2026-01-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_services_field'
down_revision = 'add_customer_contractor'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поле services в таблицу contract_data
    op.add_column('contract_data', sa.Column('services', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    # Удаляем поле services из таблицы contract_data
    op.drop_column('contract_data', 'services')
