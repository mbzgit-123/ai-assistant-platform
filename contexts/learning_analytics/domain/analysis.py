from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Profile:
    enrolled_courses: int = 0
    completed_videos: int = 0
    total_videos: int = 0
    overall_accuracy: float | None = None
    subjective_avg_score: float | None = None
    last_active_at: datetime | None = None


@dataclass
class MasteryTrendPoint:
    chapter_id: str
    period: str
    accuracy: float


@dataclass
class WeakPoint:
    chapter_id: str
    chapter_title: str | None
    accuracy: float
    reason: str


@dataclass
class StudentAnalysis:
    student_id: str
    profile: Profile
    trend: list[MasteryTrendPoint] = field(default_factory=list)
    weak_points: list[WeakPoint] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "profile": {
                "enrolledCourses": self.profile.enrolled_courses,
                "completedVideos": self.profile.completed_videos,
                "totalVideos": self.profile.total_videos,
                "overallAccuracy": self.profile.overall_accuracy,
                "subjectiveAvgScore": self.profile.subjective_avg_score,
                "lastActiveAt": (
                    self.profile.last_active_at.isoformat()
                    if self.profile.last_active_at is not None
                    else None
                ),
            },
            "trend": [
                {"chapterId": p.chapter_id, "period": p.period, "accuracy": p.accuracy}
                for p in self.trend
            ],
            "weakPoints": [
                {
                    "chapterId": w.chapter_id,
                    "chapterTitle": w.chapter_title,
                    "accuracy": w.accuracy,
                    "reason": w.reason,
                }
                for w in self.weak_points
            ],
        }
