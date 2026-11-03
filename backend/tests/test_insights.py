def test_student_stats_requires_login(client):
    assert client.get("/me/stats").status_code == 401


def test_student_stats_and_admin_analytics(student, admin):
    assert student.get("/me/stats").status_code == 200
    assert student.get("/admin/analytics").status_code == 403

    response = admin.get("/admin/analytics")
    assert response.status_code == 200
    assert {
        "companies",
        "active_jobs",
        "active_jobs_count",
        "jobs_this_week",
        "average_match",
        "topskill",
        "students",
        "early_jobs",
        "late_jobs",
        "top_posting",
    } <= response.json().keys()
