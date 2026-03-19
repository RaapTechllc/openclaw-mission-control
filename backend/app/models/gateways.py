"""Gateway model storing organization-level gateway integration metadata."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from sqlalchemy import Text, Column

from app.core.time import utcnow
from app.models.base import QueryModel

RUNTIME_ANNOTATION_TYPES = (datetime,)


class Gateway(QueryModel, table=True):
    """Configured external gateway endpoint and authentication settings."""

    __tablename__ = "gateways"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    name: str
    url: str
    token: str | None = Field(default=None, exclude=True)
    encrypted_token: str | None = Field(default=None, sa_column=Column(Text))
    disable_device_pairing: bool = Field(default=False)
    workspace_root: str
    allow_insecure_tls: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def get_decrypted_token(self) -> str | None:
        """Return the decrypted gateway token, falling back to plaintext for migration."""
        if self.encrypted_token:
            from app.core.encryption import decrypt_value
            return decrypt_value(self.encrypted_token)
        return self.token

    def set_encrypted_token(self, plaintext: str | None) -> None:
        """Encrypt and store the token, clearing the plaintext field."""
        if plaintext:
            from app.core.encryption import encrypt_value
            self.encrypted_token = encrypt_value(plaintext)
            self.token = None
        else:
            self.encrypted_token = None
            self.token = None
