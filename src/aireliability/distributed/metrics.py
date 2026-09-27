"""Optional Prometheus metrics exporter for AI Reliability Engine (Phase 24).

Defines distributed metrics:
- aireliability_jobs_total
- aireliability_jobs_completed_total
- aireliability_jobs_failed_total
- aireliability_jobs_retried_total
- aireliability_jobs_recovered_total
- aireliability_workers_active
- aireliability_workers_stale
- aireliability_execution_duration_seconds
- aireliability_job_duration_seconds
- aireliability_persistence_operations_total

Remains completely optional without hard dependency.
"""

try:
    from prometheus_client import Counter, Gauge, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class DistributedMetrics:
    """Prometheus metrics registry for distributed reliability operations."""

    def __init__(self) -> None:
        self.enabled = PROMETHEUS_AVAILABLE
        if self.enabled:
            self.jobs_total = Counter(
                "aireliability_jobs_total",
                "Total number of distributed reliability jobs created",
                ["execution_id"],
            )
            self.jobs_completed = Counter(
                "aireliability_jobs_completed_total",
                "Total number of distributed reliability jobs completed",
                ["status"],
            )
            self.jobs_failed = Counter(
                "aireliability_jobs_failed_total",
                "Total number of distributed reliability jobs failed",
                ["error_type"],
            )
            self.jobs_retried = Counter(
                "aireliability_jobs_retried_total",
                "Total number of job retry attempts executed",
            )
            self.jobs_recovered = Counter(
                "aireliability_jobs_recovered_total",
                "Total number of jobs recovered from stale workers",
            )
            self.workers_active = Gauge(
                "aireliability_workers_active",
                "Number of currently active workers",
            )
            self.workers_stale = Gauge(
                "aireliability_workers_stale",
                "Number of detected stale workers",
            )
            self.execution_duration = Histogram(
                "aireliability_execution_duration_seconds",
                "End-to-end execution duration in seconds",
            )
            self.job_duration = Histogram(
                "aireliability_job_duration_seconds",
                "Per-job execution duration in seconds",
            )
            self.persistence_operations = Counter(
                "aireliability_persistence_operations_total",
                "Total number of storage operations executed",
                ["operation", "status"],
            )
            # Phase 25 Control Plane Metrics
            self.queue_depth = Gauge(
                "aireliability_queue_depth",
                "Current number of jobs in the queue",
            )
            self.jobs_queued = Counter(
                "aireliability_jobs_queued_total",
                "Total number of jobs enqueued into the control plane",
            )
            self.jobs_scheduled = Counter(
                "aireliability_jobs_scheduled_total",
                "Total number of jobs scheduled for assignment",
            )
            self.jobs_cancelled = Counter(
                "aireliability_jobs_cancelled_total",
                "Total number of jobs cancelled",
            )
            self.jobs_assignment_failures = Counter(
                "aireliability_jobs_assignment_failures_total",
                "Total number of job assignment attempts that failed or raced",
            )
            self.job_queue_wait_seconds = Histogram(
                "aireliability_job_queue_wait_seconds",
                "Time spent waiting in queue before scheduling",
            )
            self.scheduler_dispatch_total = Counter(
                "aireliability_scheduler_dispatch_total",
                "Total number of dispatches triggered by scheduler",
            )
            self.worker_utilization = Gauge(
                "aireliability_worker_utilization",
                "Fraction of total worker capacity currently utilized",
            )
            self.scheduler_latency_seconds = Histogram(
                "aireliability_scheduler_latency_seconds",
                "Latency of scheduler dispatch evaluation in seconds",
            )
            # Phase 26 Resilience Metrics
            self.failures_total = Counter(
                "aireliability_failures_total",
                "Total number of classified failures",
                ["failure_type", "severity"],
            )
            self.retry_attempts_total = Counter(
                "aireliability_retry_attempts_total",
                "Total number of resilient retry attempts",
                ["strategy"],
            )
            self.circuit_breaker_state = Gauge(
                "aireliability_circuit_breaker_state",
                "Current state of circuit breakers (0=closed, 1=half_open, 2=open)",
                ["circuit_name"],
            )
            self.workers_quarantined = Gauge(
                "aireliability_workers_quarantined",
                "Total number of currently quarantined workers",
            )
            self.worker_recoveries_total = Counter(
                "aireliability_worker_recoveries_total",
                "Total number of worker self-healing recoveries triggered",
            )
            self.jobs_reassigned_total = Counter(
                "aireliability_jobs_reassigned_total",
                "Total number of jobs reassigned from unhealthy workers",
            )
            self.jobs_shed_total = Counter(
                "aireliability_jobs_shed_total",
                "Total number of jobs shed due to load or failure storm",
                ["reason"],
            )
            self.recovery_duration = Histogram(
                "aireliability_recovery_duration_seconds",
                "Duration of recovery operations in seconds",
            )
            # Phase 27 Multi-Tenancy Metrics
            self.tenant_jobs_total = Counter(
                "aireliability_tenant_jobs_total",
                "Total number of jobs submitted per tenant/project/namespace",
                ["tenant_id", "project_id", "namespace"],
            )
            self.tenant_jobs_failed = Counter(
                "aireliability_tenant_jobs_failed_total",
                "Total number of jobs failed per tenant/project/namespace",
                ["tenant_id", "project_id", "namespace", "error_type"],
            )
            self.tenant_jobs_retried = Counter(
                "aireliability_tenant_jobs_retried_total",
                "Total number of jobs retried per tenant",
                ["tenant_id"],
            )
            self.tenant_queue_depth = Gauge(
                "aireliability_tenant_queue_depth",
                "Current queue depth per tenant",
                ["tenant_id"],
            )
            self.tenant_active_jobs = Gauge(
                "aireliability_tenant_active_jobs",
                "Current number of concurrently active jobs per tenant",
                ["tenant_id"],
            )
            self.tenant_rate_limit_hits = Counter(
                "aireliability_tenant_rate_limit_hits",
                "Total rate limit rejections per tenant",
                ["tenant_id", "scope"],
            )
            self.tenant_quota_violations = Counter(
                "aireliability_tenant_quota_violations",
                "Total quota violations per tenant",
                ["tenant_id", "quota_type"],
            )
            self.tenant_execution_duration = Histogram(
                "aireliability_tenant_execution_duration_seconds",
                "Execution duration per tenant in seconds",
                ["tenant_id"],
            )
            # Phase 28 Security Metrics
            self.auth_attempts = Counter(
                "aireliability_authentication_attempts_total",
                "Total authentication attempts",
                ["status"],
            )
            self.auth_failures = Counter(
                "aireliability_authentication_failures_total",
                "Total authentication failures",
            )
            self.authz_denials = Counter(
                "aireliability_authorization_denials_total",
                "Total authorization denials",
            )
            self.api_keys_created = Counter(
                "aireliability_api_keys_created_total",
                "Total API keys created",
            )
            self.api_keys_revoked = Counter(
                "aireliability_api_keys_revoked_total",
                "Total API keys revoked",
            )
            self.replay_attempts = Counter(
                "aireliability_replay_attempts_total",
                "Total replay attempts detected",
            )
            self.security_rate_limits = Counter(
                "aireliability_security_rate_limits_total",
                "Total security rate limit rejections",
            )
            self.tenant_boundary_violations = Counter(
                "aireliability_tenant_boundary_violations_total",
                "Total cross-tenant boundary access violations",
            )
        else:
            self.jobs_total = None
            self.jobs_completed = None
            self.jobs_failed = None
            self.jobs_retried = None
            self.jobs_recovered = None
            self.workers_active = None
            self.workers_stale = None
            self.execution_duration = None
            self.job_duration = None
            self.persistence_operations = None
            self.queue_depth = None
            self.jobs_queued = None
            self.jobs_scheduled = None
            self.jobs_cancelled = None
            self.jobs_assignment_failures = None
            self.job_queue_wait_seconds = None
            self.scheduler_dispatch_total = None
            self.worker_utilization = None
            self.scheduler_latency_seconds = None
            self.failures_total = None
            self.retry_attempts_total = None
            self.circuit_breaker_state = None
            self.workers_quarantined = None
            self.worker_recoveries_total = None
            self.jobs_reassigned_total = None
            self.jobs_shed_total = None
            self.recovery_duration = None
            self.failure_rate = None
            # Phase 27 None defaults
            self.tenant_jobs_total = None
            self.tenant_jobs_failed = None
            self.tenant_jobs_retried = None
            self.tenant_queue_depth = None
            self.tenant_active_jobs = None
            self.tenant_rate_limit_hits = None
            self.tenant_quota_violations = None
            self.tenant_execution_duration = None
            # Phase 28 None defaults
            self.auth_attempts = None
            self.auth_failures = None
            self.authz_denials = None
            self.api_keys_created = None
            self.api_keys_revoked = None
            self.replay_attempts = None
            self.security_rate_limits = None
            self.tenant_boundary_violations = None

    def record_job_created(self, execution_id: str) -> None:
        if self.enabled and self.jobs_total:
            self.jobs_total.labels(execution_id=execution_id).inc()

    def record_job_completed(self, status: str) -> None:
        if self.enabled and self.jobs_completed:
            self.jobs_completed.labels(status=status).inc()

    def record_job_failed(self, error_type: str = "Unknown") -> None:
        if self.enabled and self.jobs_failed:
            self.jobs_failed.labels(error_type=error_type).inc()

    def record_job_retry(self) -> None:
        if self.enabled and self.jobs_retried:
            self.jobs_retried.inc()

    def record_job_recovered(self) -> None:
        if self.enabled and self.jobs_recovered:
            self.jobs_recovered.inc()

    def set_active_workers(self, count: int) -> None:
        if self.enabled and self.workers_active:
            self.workers_active.set(count)

    def set_stale_workers(self, count: int) -> None:
        if self.enabled and self.workers_stale:
            self.workers_stale.set(count)

    def record_persistence_op(self, operation: str, status: str = "success") -> None:
        if self.enabled and self.persistence_operations:
            self.persistence_operations.labels(operation=operation, status=status).inc()

    # Phase 25 Recording Methods
    def set_queue_depth(self, depth: int) -> None:
        if self.enabled and self.queue_depth:
            self.queue_depth.set(depth)

    def record_job_queued(self) -> None:
        if self.enabled and self.jobs_queued:
            self.jobs_queued.inc()

    def record_job_scheduled(self) -> None:
        if self.enabled and self.jobs_scheduled:
            self.jobs_scheduled.inc()

    def record_job_cancelled(self) -> None:
        if self.enabled and self.jobs_cancelled:
            self.jobs_cancelled.inc()

    def record_assignment_failure(self) -> None:
        if self.enabled and self.jobs_assignment_failures:
            self.jobs_assignment_failures.inc()

    def record_queue_wait(self, duration_seconds: float) -> None:
        if self.enabled and self.job_queue_wait_seconds:
            self.job_queue_wait_seconds.observe(duration_seconds)

    def record_scheduler_dispatch(self) -> None:
        if self.enabled and self.scheduler_dispatch_total:
            self.scheduler_dispatch_total.inc()

    def set_worker_utilization(self, ratio: float) -> None:
        if self.enabled and self.worker_utilization:
            self.worker_utilization.set(ratio)

    def record_scheduler_latency(self, duration_seconds: float) -> None:
        if self.enabled and self.scheduler_latency_seconds:
            self.scheduler_latency_seconds.observe(duration_seconds)

    # Phase 26 Resilience Recording Methods
    def record_failure_metric(self, failure_type: str, severity: str) -> None:
        if self.enabled and self.failures_total:
            self.failures_total.labels(
                failure_type=failure_type, severity=severity
            ).inc()

    def record_retry_attempt(self, strategy: str = "none") -> None:
        if self.enabled and self.retry_attempts_total:
            self.retry_attempts_total.labels(strategy=strategy).inc()

    def set_circuit_state(self, circuit_name: str, state_value: int) -> None:
        if self.enabled and self.circuit_breaker_state:
            self.circuit_breaker_state.labels(circuit_name=circuit_name).set(
                state_value
            )

    def set_quarantined_workers(self, count: int) -> None:
        if self.enabled and self.workers_quarantined:
            self.workers_quarantined.set(count)

    def record_worker_recovery(self) -> None:
        if self.enabled and self.worker_recoveries_total:
            self.worker_recoveries_total.inc()

    def record_job_reassigned(self) -> None:
        if self.enabled and self.jobs_reassigned_total:
            self.jobs_reassigned_total.inc()

    def record_job_shed(self, reason: str = "overload") -> None:
        if self.enabled and self.jobs_shed_total:
            self.jobs_shed_total.labels(reason=reason).inc()

    def record_recovery_duration(self, duration_seconds: float) -> None:
        if self.enabled and self.recovery_duration:
            self.recovery_duration.observe(duration_seconds)

    def set_failure_rate(self, rate: float) -> None:
        if self.enabled and self.failure_rate:
            self.failure_rate.set(rate)

    # Phase 27 Tenancy Recording Methods
    def record_tenant_job(
        self,
        tenant_id: str = "default",
        project_id: str = "default",
        namespace: str = "default",
    ) -> None:
        if self.enabled and self.tenant_jobs_total:
            self.tenant_jobs_total.labels(
                tenant_id=tenant_id,
                project_id=project_id,
                namespace=namespace,
            ).inc()

    def record_tenant_job_failed(
        self,
        tenant_id: str = "default",
        project_id: str = "default",
        namespace: str = "default",
        error_type: str = "Unknown",
    ) -> None:
        if self.enabled and self.tenant_jobs_failed:
            self.tenant_jobs_failed.labels(
                tenant_id=tenant_id,
                project_id=project_id,
                namespace=namespace,
                error_type=error_type,
            ).inc()

    def record_tenant_job_retried(self, tenant_id: str = "default") -> None:
        if self.enabled and self.tenant_jobs_retried:
            self.tenant_jobs_retried.labels(tenant_id=tenant_id).inc()

    def set_tenant_queue_depth(self, tenant_id: str, depth: int) -> None:
        if self.enabled and self.tenant_queue_depth:
            self.tenant_queue_depth.labels(tenant_id=tenant_id).set(depth)

    def set_tenant_active_jobs(self, tenant_id: str, active: int) -> None:
        if self.enabled and self.tenant_active_jobs:
            self.tenant_active_jobs.labels(tenant_id=tenant_id).set(active)

    def record_tenant_rate_limit_hit(
        self, tenant_id: str, scope: str = "tenant"
    ) -> None:
        if self.enabled and self.tenant_rate_limit_hits:
            self.tenant_rate_limit_hits.labels(tenant_id=tenant_id, scope=scope).inc()

    def record_tenant_quota_violation(self, tenant_id: str, quota_type: str) -> None:
        if self.enabled and self.tenant_quota_violations:
            self.tenant_quota_violations.labels(
                tenant_id=tenant_id, quota_type=quota_type
            ).inc()

    def record_tenant_duration(self, tenant_id: str, duration_seconds: float) -> None:
        if self.enabled and self.tenant_execution_duration:
            self.tenant_execution_duration.labels(tenant_id=tenant_id).observe(
                duration_seconds
            )

    # --- Phase 28 Security Recorders ---

    def record_auth_attempt(self, success: bool = True) -> None:
        if self.enabled and self.auth_attempts:
            status = "success" if success else "failure"
            self.auth_attempts.labels(status=status).inc()
        if not success and self.enabled and self.auth_failures:
            self.auth_failures.inc()

    def record_authz_denial(self) -> None:
        if self.enabled and self.authz_denials:
            self.authz_denials.inc()

    def record_api_key_created(self) -> None:
        if self.enabled and self.api_keys_created:
            self.api_keys_created.inc()

    def record_api_key_revoked(self) -> None:
        if self.enabled and self.api_keys_revoked:
            self.api_keys_revoked.inc()

    def record_replay_attempt(self) -> None:
        if self.enabled and self.replay_attempts:
            self.replay_attempts.inc()

    def record_security_rate_limit(self) -> None:
        if self.enabled and self.security_rate_limits:
            self.security_rate_limits.inc()

    def record_tenant_boundary_violation(self) -> None:
        if self.enabled and self.tenant_boundary_violations:
            self.tenant_boundary_violations.inc()
