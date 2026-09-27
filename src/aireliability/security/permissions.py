"""Explicit permissions definitions and manager for Phase 28."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    """Explicit permission item defining an action on a target scope."""

    name: str
    description: str = ""
    category: str = "general"


# Standard explicit permissions
PERM_JOBS_READ = "jobs.read"
PERM_JOBS_SUBMIT = "jobs.submit"
PERM_JOBS_CANCEL = "jobs.cancel"
PERM_JOBS_RETRY = "jobs.retry"

PERM_EXECUTIONS_READ = "executions.read"
PERM_EXECUTIONS_CANCEL = "executions.cancel"

PERM_WORKERS_READ = "workers.read"
PERM_WORKERS_MANAGE = "workers.manage"

PERM_TENANTS_READ = "tenants.read"
PERM_TENANTS_MANAGE = "tenants.manage"

PERM_QUOTAS_READ = "quotas.read"
PERM_QUOTAS_MANAGE = "quotas.manage"

PERM_RESILIENCE_READ = "resilience.read"
PERM_RESILIENCE_MANAGE = "resilience.manage"

PERM_SCHEDULER_READ = "scheduler.read"
PERM_SCHEDULER_MANAGE = "scheduler.manage"

PERM_SECURITY_READ = "security.read"
PERM_SECURITY_MANAGE = "security.manage"

ALL_STANDARD_PERMISSIONS = {
    PERM_JOBS_READ: Permission(PERM_JOBS_READ, "Read jobs", "jobs"),
    PERM_JOBS_SUBMIT: Permission(PERM_JOBS_SUBMIT, "Submit new jobs", "jobs"),
    PERM_JOBS_CANCEL: Permission(PERM_JOBS_CANCEL, "Cancel active jobs", "jobs"),
    PERM_JOBS_RETRY: Permission(PERM_JOBS_RETRY, "Retry failed jobs", "jobs"),
    PERM_EXECUTIONS_READ: Permission(
        PERM_EXECUTIONS_READ, "Read execution runs", "executions"
    ),
    PERM_EXECUTIONS_CANCEL: Permission(
        PERM_EXECUTIONS_CANCEL, "Cancel runs", "executions"
    ),
    PERM_WORKERS_READ: Permission(PERM_WORKERS_READ, "Read worker records", "workers"),
    PERM_WORKERS_MANAGE: Permission(
        PERM_WORKERS_MANAGE, "Manage/quarantine workers", "workers"
    ),
    PERM_TENANTS_READ: Permission(PERM_TENANTS_READ, "Read tenant info", "tenants"),
    PERM_TENANTS_MANAGE: Permission(PERM_TENANTS_MANAGE, "Manage tenants", "tenants"),
    PERM_QUOTAS_READ: Permission(PERM_QUOTAS_READ, "Read resource quotas", "quotas"),
    PERM_QUOTAS_MANAGE: Permission(PERM_QUOTAS_MANAGE, "Manage quotas", "quotas"),
    PERM_RESILIENCE_READ: Permission(
        PERM_RESILIENCE_READ, "Read resilience info", "resilience"
    ),
    PERM_RESILIENCE_MANAGE: Permission(
        PERM_RESILIENCE_MANAGE, "Manage resilience", "resilience"
    ),
    PERM_SCHEDULER_READ: Permission(
        PERM_SCHEDULER_READ, "Read scheduler status", "scheduler"
    ),
    PERM_SCHEDULER_MANAGE: Permission(
        PERM_SCHEDULER_MANAGE, "Control scheduler", "scheduler"
    ),
    PERM_SECURITY_READ: Permission(
        PERM_SECURITY_READ, "Read security audit/keys", "security"
    ),
    PERM_SECURITY_MANAGE: Permission(
        PERM_SECURITY_MANAGE, "Manage security credentials", "security"
    ),
}


class PermissionManager:
    """Registry and checker for granular security permissions."""

    def __init__(self) -> None:
        self._permissions: dict[str, Permission] = dict(ALL_STANDARD_PERMISSIONS)

    def register_permission(self, permission: Permission) -> None:
        """Register a custom permission."""
        self._permissions[permission.name] = permission

    def get_permission(self, name: str) -> Permission | None:
        """Retrieve a permission definition."""
        return self._permissions.get(name)

    def list_permissions(self) -> list[Permission]:
        """List all registered permissions."""
        return list(self._permissions.values())

    def implies(self, granted_permission: str, required_permission: str) -> bool:
        """Check if a granted permission satisfies the required permission.

        Supports wildcard hierarchy, e.g. 'jobs.*' satisfies 'jobs.read',
        and '*' satisfies all.
        """
        if granted_permission == "*":
            return True
        if granted_permission == required_permission:
            return True
        if granted_permission.endswith(".*"):
            prefix = granted_permission[:-2]
            return required_permission.startswith(prefix + ".")
        return False
