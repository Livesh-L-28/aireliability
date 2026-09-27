"""Role-Based Access Control (RBAC) definitions and RoleManager for Phase 28."""

from dataclasses import dataclass, field
from enum import StrEnum

from aireliability.security.permissions import (
    ALL_STANDARD_PERMISSIONS,
    PERM_EXECUTIONS_CANCEL,
    PERM_EXECUTIONS_READ,
    PERM_JOBS_CANCEL,
    PERM_JOBS_READ,
    PERM_JOBS_RETRY,
    PERM_JOBS_SUBMIT,
    PERM_QUOTAS_READ,
    PERM_RESILIENCE_MANAGE,
    PERM_RESILIENCE_READ,
    PERM_SCHEDULER_MANAGE,
    PERM_SCHEDULER_READ,
    PERM_SECURITY_MANAGE,
    PERM_SECURITY_READ,
    PERM_TENANTS_READ,
    PERM_WORKERS_MANAGE,
    PERM_WORKERS_READ,
)


class BuiltinRole(StrEnum):
    """Standard built-in system roles."""

    ADMIN = "ADMIN"
    TENANT_ADMIN = "TENANT_ADMIN"
    PROJECT_ADMIN = "PROJECT_ADMIN"
    OPERATOR = "OPERATOR"
    DEVELOPER = "DEVELOPER"
    VIEWER = "VIEWER"
    WORKER = "WORKER"
    SERVICE = "SERVICE"


@dataclass(frozen=True)
class Role:
    """Named role aggregating explicit permissions."""

    name: str
    description: str = ""
    permissions: frozenset[str] = field(default_factory=frozenset)


STANDARD_ROLES = {
    BuiltinRole.ADMIN: Role(
        name=BuiltinRole.ADMIN,
        description="Global administrator with full system capabilities",
        permissions=frozenset(ALL_STANDARD_PERMISSIONS.keys()),
    ),
    BuiltinRole.TENANT_ADMIN: Role(
        name=BuiltinRole.TENANT_ADMIN,
        description="Administrator of a specific tenant",
        permissions=frozenset(
            [
                PERM_JOBS_READ,
                PERM_JOBS_SUBMIT,
                PERM_JOBS_CANCEL,
                PERM_JOBS_RETRY,
                PERM_EXECUTIONS_READ,
                PERM_EXECUTIONS_CANCEL,
                PERM_WORKERS_READ,
                PERM_TENANTS_READ,
                PERM_QUOTAS_READ,
                PERM_RESILIENCE_READ,
                PERM_SCHEDULER_READ,
                PERM_SECURITY_READ,
                PERM_SECURITY_MANAGE,
            ]
        ),
    ),
    BuiltinRole.PROJECT_ADMIN: Role(
        name=BuiltinRole.PROJECT_ADMIN,
        description="Administrator of a project within a tenant",
        permissions=frozenset(
            [
                PERM_JOBS_READ,
                PERM_JOBS_SUBMIT,
                PERM_JOBS_CANCEL,
                PERM_JOBS_RETRY,
                PERM_EXECUTIONS_READ,
                PERM_EXECUTIONS_CANCEL,
                PERM_WORKERS_READ,
                PERM_RESILIENCE_READ,
                PERM_SECURITY_READ,
            ]
        ),
    ),
    BuiltinRole.OPERATOR: Role(
        name=BuiltinRole.OPERATOR,
        description="Platform operations engineer",
        permissions=frozenset(
            [
                PERM_JOBS_READ,
                PERM_JOBS_CANCEL,
                PERM_JOBS_RETRY,
                PERM_EXECUTIONS_READ,
                PERM_EXECUTIONS_CANCEL,
                PERM_WORKERS_READ,
                PERM_WORKERS_MANAGE,
                PERM_TENANTS_READ,
                PERM_QUOTAS_READ,
                PERM_RESILIENCE_READ,
                PERM_RESILIENCE_MANAGE,
                PERM_SCHEDULER_READ,
                PERM_SCHEDULER_MANAGE,
            ]
        ),
    ),
    BuiltinRole.DEVELOPER: Role(
        name=BuiltinRole.DEVELOPER,
        description="Standard reliability engineer / developer",
        permissions=frozenset(
            [
                PERM_JOBS_READ,
                PERM_JOBS_SUBMIT,
                PERM_JOBS_RETRY,
                PERM_EXECUTIONS_READ,
                PERM_WORKERS_READ,
                PERM_RESILIENCE_READ,
            ]
        ),
    ),
    BuiltinRole.VIEWER: Role(
        name=BuiltinRole.VIEWER,
        description="Read-only observer",
        permissions=frozenset(
            [
                PERM_JOBS_READ,
                PERM_EXECUTIONS_READ,
                PERM_WORKERS_READ,
                PERM_TENANTS_READ,
                PERM_QUOTAS_READ,
                PERM_RESILIENCE_READ,
                PERM_SCHEDULER_READ,
            ]
        ),
    ),
    BuiltinRole.WORKER: Role(
        name=BuiltinRole.WORKER,
        description="Execution node worker identity",
        permissions=frozenset(
            [
                PERM_JOBS_READ,
                PERM_EXECUTIONS_READ,
                PERM_WORKERS_READ,
            ]
        ),
    ),
    BuiltinRole.SERVICE: Role(
        name=BuiltinRole.SERVICE,
        description="Background or API integration service",
        permissions=frozenset(
            [
                PERM_JOBS_READ,
                PERM_JOBS_SUBMIT,
                PERM_EXECUTIONS_READ,
            ]
        ),
    ),
}


class RoleManager:
    """Manages role registrations and maps roles to permission sets."""

    def __init__(self) -> None:
        self._roles: dict[str, Role] = dict(STANDARD_ROLES)

    def register_role(self, role: Role) -> None:
        """Register or override a custom role."""
        self._roles[role.name] = role

    def get_role(self, name: str) -> Role | None:
        """Retrieve role definition by name."""
        return self._roles.get(name)

    def list_roles(self) -> list[Role]:
        """List all available roles."""
        return list(self._roles.values())

    def get_permissions_for_roles(self, role_names: list[str]) -> set[str]:
        """Collect all aggregated permissions for a list of roles."""
        perms: set[str] = set()
        for r_name in role_names:
            role = self._roles.get(r_name)
            if role:
                perms.update(role.permissions)
        return perms
