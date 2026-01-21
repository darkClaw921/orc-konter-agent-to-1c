"""add customer and contractor fields

Revision ID: add_customer_contractor
Revises: d9809eeeef7a
Create Date: 2026-01-18 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_customer_contractor'
down_revision = 'd9809eeeef7a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поля customer и contractor в таблицу contract_data
    op.add_column('contract_data', sa.Column('customer', postgresql.JSONB(), nullable=True))
    op.add_column('contract_data', sa.Column('contractor', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    # Удаляем поля customer и contractor из таблицы contract_data
    op.drop_column('contract_data', 'contractor')
    op.drop_column('contract_data', 'customer')
