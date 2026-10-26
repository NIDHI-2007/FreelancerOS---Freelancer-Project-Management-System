"""Helpers for writing notifications inside an existing database transaction."""

from datetime import datetime, timedelta


def add_notification(cursor, user_id, message, notification_type):
    """Insert a notification using the caller's cursor and transaction.

    The existing Notification table has no event-key column. Exact duplicate
    deliveries are therefore suppressed for the same recipient/type/message
    within a short retry window; event messages should include their entity ID.
    Business routes still own commit/rollback so notifications remain atomic.
    """
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1:
        raise ValueError("Notification recipient must be a positive user ID.")
    if not isinstance(message, str) or not message.strip() or len(message.strip()) > 1000:
        raise ValueError("Notification message must contain 1–1000 characters.")
    if not isinstance(notification_type, str) or not notification_type.strip() or len(notification_type.strip()) > 40:
        raise ValueError("Notification type must contain 1–40 characters.")

    message = message.strip()
    notification_type = notification_type.strip().lower()
    cursor.execute("SELECT 1 FROM `User` WHERE user_id = %s", (user_id,))
    if cursor.fetchone() is None:
        raise ValueError("Notification recipient does not exist.")

    cursor.execute("SELECT CURRENT_TIMESTAMP")
    current_time = cursor.fetchone()
    if isinstance(current_time, dict):
        current_time = next(iter(current_time.values()))
    else:
        current_time = current_time[0]
    if isinstance(current_time, str):
        current_time = datetime.fromisoformat(current_time)
    retry_window_start = current_time.replace(microsecond=0) - timedelta(seconds=30)
    cursor.execute(
        "SELECT 1 FROM Notification WHERE user_id = %s AND notification_type = %s "
        "AND message = %s AND created_at >= %s LIMIT 1",
        (user_id, notification_type, message, retry_window_start),
    )
    if cursor.fetchone() is not None:
        return False

    cursor.execute(
        "INSERT INTO Notification (user_id, message, notification_type) VALUES (%s, %s, %s)",
        (user_id, message, notification_type),
    )
    return True


def notify_project_applicants(cursor, project_id, title, status, exclude_user_id=None):
    """Notify applicants still awaiting a decision about a project status change."""
    query = (
        "SELECT freelancer_id FROM Application WHERE project_id = %s "
        "AND status IN ('pending','shortlisted')"
    )
    params = [project_id]
    if exclude_user_id is not None:
        query += " AND freelancer_id <> %s"
        params.append(exclude_user_id)
    query += " ORDER BY freelancer_id"
    cursor.execute(query, tuple(params))
    for row in cursor.fetchall():
        freelancer_id = row["freelancer_id"] if isinstance(row, dict) else row[0]
        add_notification(
            cursor,
            freelancer_id,
            f'Project "{title}" (project #{project_id}) is now {status.replace("_", " ")}.',
            "project_status_changed",
        )


def notify_matching_freelancers(cursor, project_id, client_id, title, notification_type="project_created"):
    """Notify active freelancers with at least one skill required by a project."""
    cursor.execute(
        "SELECT DISTINCT fs.freelancer_id FROM Project_Skill ps "
        "JOIN Freelancer_Skill fs ON fs.skill_id = ps.skill_id "
        "JOIN Freelancer f ON f.user_id = fs.freelancer_id "
        "JOIN `User` u ON u.user_id = fs.freelancer_id "
        "WHERE ps.project_id = %s AND u.role = 'freelancer' AND u.account_status = 'active' "
        "AND f.availability_status IN ('available','busy') AND fs.freelancer_id <> %s",
        (project_id, client_id),
    )
    for row in cursor.fetchall():
        freelancer_id = row["freelancer_id"] if isinstance(row, dict) else row[0]
        message = (
            f'New project matching your skills: "{title}" (project #{project_id}) is open.'
            if notification_type == "project_created"
            else f'Project "{title}" (project #{project_id}) is now open and matches your skills.'
        )
        add_notification(cursor, freelancer_id, message, notification_type)
