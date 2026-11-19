from dataclasses import dataclass

MIN_TOTAL_SECONDS = 1800  # 30 分钟下限（<30 block）
ALLOW_THRESHOLD_SECONDS = 3600  # 60 分钟放行阈值（30-60 soft）
MAX_TOTAL_SECONDS = 5400  # 90 分钟上限（>90 over）


@dataclass
class AdmissionResult:
    level: str  # "block" | "soft" | "allow" | "over"
    total_seconds: int
    shortfall_seconds: int  # 距 60 分钟放行线的差值（allow/over 为 0）


def check_admission(total_seconds: int) -> AdmissionResult:
    if total_seconds > MAX_TOTAL_SECONDS:
        return AdmissionResult("over", total_seconds, 0)
    if total_seconds >= ALLOW_THRESHOLD_SECONDS:
        return AdmissionResult("allow", total_seconds, 0)
    if total_seconds >= MIN_TOTAL_SECONDS:
        return AdmissionResult("soft", total_seconds, ALLOW_THRESHOLD_SECONDS - total_seconds)
    return AdmissionResult("block", total_seconds, ALLOW_THRESHOLD_SECONDS - total_seconds)
