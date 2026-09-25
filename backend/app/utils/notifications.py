"""Helpers for writing notifications inside an existing database transaction."""


def add_notification(cursor, user_id, message, notification_type):
    cursor.execute(
        "INSERT INTO Notification (user_id, message, notification_type) VALUES (%s, %s, %s)",
        (user_id, message, notification_type),
    )
