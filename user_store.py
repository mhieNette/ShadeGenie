import json
from db import get_db_connection


def get_user(username: str):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()
    return user


def create_user(username: str, password: str, email: str = None, age: int = None):
    """
    Creates a normal (non-admin) user.
    - email can be None
    - age can be None or int
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO users (username, password, email, age)
        VALUES (%s, %s, %s, %s)
        """,
        (username, password, email, age)
    )

    conn.commit()
    cursor.close()
    conn.close()


def update_profile_photo(username: str, photo_path: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET profile_photo = %s WHERE username = %s",
        (photo_path, username)
    )

    conn.commit()
    cursor.close()
    conn.close()


def save_foundation_suggestions(username: str, suggestions):
    """
    Saves suggestions as JSON into users.foundation_suggestions (TEXT / JSON string).
    suggestions must be a list (usually list of dicts).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    suggestions_json = json.dumps(suggestions, ensure_ascii=False)

    cursor.execute(
        "UPDATE users SET foundation_suggestions = %s WHERE username = %s",
        (suggestions_json, username)
    )

    conn.commit()
    cursor.close()
    conn.close()


def load_foundation_suggestions(user_or_username):
    """
    Accepts either:
      - username (str), OR
      - user dict returned by get_user()

    Returns: list of dicts
    """
    # 1) Normalize input -> username
    if isinstance(user_or_username, dict):
        username = user_or_username.get("username")
    else:
        username = user_or_username

    if not username:
        return []

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT foundation_suggestions FROM users WHERE username = %s",
        (username,)
    )
    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        return []

    raw = row.get("foundation_suggestions")
    if not raw:
        return []

    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT username, email, age, profile_photo, is_admin FROM users")
    users = cursor.fetchall()

    cursor.close()
    conn.close()
    return users


def delete_user(username: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM users WHERE username = %s", (username,))
    conn.commit()

    cursor.close()
    conn.close()
