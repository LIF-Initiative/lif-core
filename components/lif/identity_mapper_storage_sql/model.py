from uuid import uuid4

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from lif.identity_mapper_storage_sql.db import Base
from lif.datatypes import IdentityMapping


class IdentityMappingModel(Base):
    """SQLAlchemy model for identity mappings."""

    __tablename__ = "identity_mappings"

    mapping_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True, default=lambda: str(uuid4()))
    lif_organization_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    lif_organization_person_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    target_system_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    target_system_person_id_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    target_system_person_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "lif_organization_id",
            "lif_organization_person_id",
            "target_system_id",
            "target_system_person_id_type",
            name="uq_identity_mapping",
        ),
    )

    def from_identity_mapping(self, identity_mapping: IdentityMapping):
        self.mapping_id = identity_mapping.mapping_id
        self.lif_organization_id = identity_mapping.lif_organization_id
        self.lif_organization_person_id = identity_mapping.lif_organization_person_id
        self.target_system_id = identity_mapping.target_system_id
        self.target_system_person_id_type = identity_mapping.target_system_person_id_type
        self.target_system_person_id = identity_mapping.target_system_person_id
