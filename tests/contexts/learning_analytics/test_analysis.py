from datetime import datetime

from contexts.learning_analytics.domain.analysis import (
    MasteryTrendPoint,
    Profile,
    StudentAnalysis,
    WeakPoint,
)


def test_student_analysis_to_dict_serializes_all_sections():
    analysis = StudentAnalysis(
        student_id="s1",
        profile=Profile(
            enrolled_courses=2,
            completed_videos=3,
            total_videos=10,
            overall_accuracy=0.8,
            subjective_avg_score=72.5,
            last_active_at=datetime(2026, 11, 18, 12, 0, 0),
        ),
        trend=[MasteryTrendPoint(course_id="ch1", course_title="循环结构", period="2026-11-18", accuracy=0.75)],
        weak_points=[
            WeakPoint(course_id="ch2", course_title="循环结构", accuracy=0.4, reason="未掌握 break")
        ],
    )
    assert analysis.to_dict() == {
        "profile": {
            "enrolledCourses": 2,
            "completedVideos": 3,
            "totalVideos": 10,
            "overallAccuracy": 0.8,
            "subjectiveAvgScore": 72.5,
            "lastActiveAt": "2026-11-18T12:00:00",
        },
        "trend": [
            {"courseId": "ch1", "courseTitle": "循环结构", "period": "2026-11-18", "accuracy": 0.75},
        ],
        "weakPoints": [
            {
                "courseId": "ch2",
                "courseTitle": "循环结构",
                "accuracy": 0.4,
                "reason": "未掌握 break",
            }
        ],
    }


def test_profile_defaults_to_zero_and_none():
    p = Profile()
    assert p.enrolled_courses == 0
    assert p.overall_accuracy is None
    assert p.last_active_at is None
