"""Workspace settings. Admins edit these on the Settings page today."""
from dataclasses import dataclass, field


@dataclass
class WorkspaceSettings:
    timezone: str = "UTC"
    locale: str = "en-US"
    sso_enforced: bool = False
    notification_email: str = ""
    retention_days: int = 365
    custom_fields: dict = field(default_factory=dict)  # admin-defined; often 20+ entries
