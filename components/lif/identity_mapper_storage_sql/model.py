from uuid import uuid4

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from lif.identity_mapper_storage_sql.db import Base
from lif.datatypes import IdentityMapping


class IdentityMappingModel(Base):
    """SQLAlchemy model for identity mappings."""

    __tablename__ = "identity_mappings"

    mapping_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lif_organization_id: Mapped[str] = mapped_column(String(255), nullable=False)
    lif_organization_person_id: Mapped[str] = mapped_column(String(255), nullable=False)
    target_system_id: Mapped[str] = mapped_column(String(255), nullable=False)
    target_system_person_id_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_system_person_id: Mapped[str] = mapped_column(String(255), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "lif_organization_id",
            "lif_organization_person_id",
            "target_system_id",
            "target_system_person_id_type",
            name="uq_identity_mapping",
        ),
        # Mirrors projects/lif_identity_mapper_mariadb/02-ddl.sql, which is what production
        # actually runs; this declaration only takes effect under
        # IDENTITY_MAPPER_DB_AUTO_CREATE_TABLES. Keep the two in sync -- see that file for why
        # uq_identity_mapping cannot serve read_by_lif_org_and_person and why this index's
        # column widths are load-bearing (#1231).
        Index("idx_org_person", "lif_organization_id", "lif_organization_person_id"),
    )

    def from_identity_mapping(self, identity_mapping: IdentityMapping):
        # mapping_id is Optional on the DTO. Generate it here rather than leaning on the
        # column default: the batch save adds every new row and flushes once, so the PK
        # has to exist before that flush for callers to read it back.
        self.mapping_id = identity_mapping.mapping_id or str(uuid4())
        self.lif_organization_id = identity_mapping.lif_organization_id
        self.lif_organization_person_id = identity_mapping.lif_organization_person_id
        self.target_system_id = identity_mapping.target_system_id
        self.target_system_person_id_type = identity_mapping.target_system_person_id_type
        self.target_system_person_id = identity_mapping.target_system_person_id
