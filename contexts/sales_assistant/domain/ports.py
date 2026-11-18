from typing import Protocol

from shared.infrastructure.db.models.business import Lead


class VipReportPort(Protocol):
    def report_vip(self, lead: Lead) -> bool: ...
