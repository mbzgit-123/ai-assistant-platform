from dataclasses import dataclass

MIN_TOTAL_SECONDS = 3600  # 60 分钟放行阈值
SOFT_THRESHOLD_SECONDS = 1800  # 30 分钟软提示下限


@dataclass
class AdmissionResult:
    level: str  # "block" | "soft" | "allow"
    total_seconds: int
    shortfall_seconds: int  # 0 when allowed


def check_admission(total_seconds: int) -> AdmissionResult:
    if total_seconds >= MIN_TOTAL_SECONDS:
        return AdmissionResult("allow", total_seconds, 0)
    if total_seconds >= SOFT_THRESHOLD_SECONDS:
        return AdmissionResult("soft", total_seconds, MIN_TOTAL_SECONDS - total_seconds)
    return AdmissionResult("block", total_seconds, MIN_TOTAL_SECONDS - total_seconds)
