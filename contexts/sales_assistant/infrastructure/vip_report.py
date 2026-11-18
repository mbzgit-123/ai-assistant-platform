from shared.infrastructure.db.models.business import Lead


class StubVipReport:
    def report_vip(self, lead: Lead) -> bool:
        return True
