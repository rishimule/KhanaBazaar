"""address_geo_columns

Revision ID: 3e36788adecf
Revises: 8bd3769f0789
Create Date: 2026-05-06 22:27:28.389836

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '3e36788adecf'
down_revision: Union[str, Sequence[str], None] = '8bd3769f0789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'address',
        sa.Column('digipin', sqlmodel.sql.sqltypes.AutoString(length=12), nullable=True),
    )
    op.add_column(
        'address',
        sa.Column('place_id', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    )
    location_source_enum = sa.Enum(
        'manual', 'autocomplete', 'pin', 'geocoded', name='locationsource'
    )
    location_source_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'address',
        sa.Column(
            'location_source',
            sa.Enum(name='locationsource', create_type=False),
            nullable=True,
        ),
    )
    op.execute(
        "ALTER TABLE address ADD COLUMN geo geography(Point, 4326) "
        "GENERATED ALWAYS AS ("
        "  CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL "
        "       THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography "
        "       ELSE NULL END"
        ") STORED"
    )
    op.execute("CREATE INDEX ix_address_geo ON address USING GIST (geo)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_address_geo")
    op.execute("ALTER TABLE address DROP COLUMN IF EXISTS geo")
    op.drop_column('address', 'location_source')
    op.drop_column('address', 'place_id')
    op.drop_column('address', 'digipin')
    op.execute("DROP TYPE IF EXISTS locationsource")
