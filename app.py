from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from functools import wraps
from uuid import uuid4
import os
import json
import sqlite3
from datetime import datetime
from PIL import Image
from sample_colors import sample_colors, get_sample_color

from user_store import (
    get_user,
    create_user,
    update_profile_photo,
    get_all_users,
    delete_user,
    save_foundation_suggestions,
    load_foundation_suggestions
)

# -------------------------
# PATHS / CONSTANTS
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "shadegenie")

FOUNDATION_SHADES_FILE = os.path.join(BASE_DIR, "foundation_shades.json")

# -------------------------
# APP SETUP
# -------------------------
app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # TODO: move to env var in production

# Uploads
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# -------------------------
# DATABASE INIT (Feedback)
# -------------------------
def init_db():
    """Create required tables if they don't exist yet."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment TEXT NOT NULL,
            date TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

init_db()


# -------------------------
# HELPERS
# -------------------------

def get_current_user():
    username = session.get('username')
    if not username:
        return None
    return get_user(username)


def is_admin_user():
    user = get_current_user()
    return bool(user and user.get('is_admin'))

def clear_upload_state():
    session.pop("quiz", None)
    session.pop("quiz_owner", None)
    session.pop("image_url", None)
    session.pop("image_path", None)

def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login_page'))

        user = get_user(session['username'])
        if not user or not user.get('is_admin'):
            flash("Admin access only.")
            return redirect(url_for('profile'))

        return view_func(*args, **kwargs)
    return wrapped


def user_upload_folder(username: str) -> str:
    # physical folder inside static/uploads/<username>/
    return os.path.join(app.config['UPLOAD_FOLDER'], username)


def ensure_user_folder(username: str):
    os.makedirs(user_upload_folder(username), exist_ok=True)


def safe_user_image_url(username: str, filename: str) -> str:
    # URL like /static/uploads/<username>/<filename>
    return f"/static/uploads/{username}/{filename}"


def image_belongs_to_user(username: str, photo_url: str) -> bool:
    prefix = f"/static/uploads/{username}/"
    return bool(photo_url) and photo_url.startswith(prefix)


# -------------------------
# QUIZ HELPERS (3 QUESTIONS)
# -------------------------

def get_quiz_from_form(form):
    """
    Reads the 3 questions:
    - skin_tone: fair/light/medium/tan/deep
    - undertone: warm/cool/neutral/olive
    - jewelry: gold/silver/both/rose_gold/etc (we only use gold/silver/both for inference)
    """
    return {
        "skin_tone": (form.get("skin_tone") or "").strip(),
        "undertone": (form.get("undertone") or "").strip(),
        "jewelry": (form.get("jewelry") or "").strip(),
    }


def quiz_is_complete(quiz: dict) -> bool:
    required = ["skin_tone", "undertone", "jewelry"]
    return bool(quiz) and all(str(quiz.get(k) or "").strip() for k in required)


# -------------------------
# SHADE CATALOG HELPERS
# -------------------------

def load_foundation_shades():
    if not os.path.exists(FOUNDATION_SHADES_FILE):
        return []

    with open(FOUNDATION_SHADES_FILE, 'r', encoding='utf-8') as f:
        shades = json.load(f) or []

    # Ensure each has id + matching fields
    for i, s in enumerate(shades):
        if 'id' not in s or not str(s.get('id')).strip():
            s['id'] = str(i + 1)
        if 'tone_bucket' not in s:
            s['tone_bucket'] = ''
        if 'undertone' not in s:
            s['undertone'] = ''

    return shades


def save_foundation_shades(shades):
    with open(FOUNDATION_SHADES_FILE, 'w', encoding='utf-8') as f:
        json.dump(shades, f, indent=2, ensure_ascii=False)


# -------------------------
# MATCHING HELPERS
# -------------------------

def _hex_to_rgb(hex_color: str):
    if not hex_color:
        return None
    s = str(hex_color).strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return None


def _norm(s: str) -> str:
    return " ".join(str(s or "").strip().lower().split())


def suggest_shades(image_path, k=2, quiz=None):
    """
    1) Filter by quiz tone_bucket + undertone (warm also matches olive)
    2) Rank by closest sample_colors hex to photo average color
    3) Fallback brightness if sample color missing
    Returns exactly k suggestions.
    """
    quiz = quiz or {}

    if not os.path.exists(FOUNDATION_SHADES_FILE):
        return []

    with open(FOUNDATION_SHADES_FILE, 'r', encoding='utf-8') as f:
        shades = json.load(f) or []

    if not shades:
        return []

    skin_tone = _norm(quiz.get("skin_tone"))
    undertone = _norm(quiz.get("undertone"))
    jewelry = _norm(quiz.get("jewelry"))

    # Infer undertone if missing (optional fallback)
    if not undertone:
        if jewelry == "gold":
            undertone = "warm"
        elif jewelry == "silver":
            undertone = "cool"
        elif jewelry == "both":
            undertone = "neutral"

    def tone_of(s): 
        return _norm(s.get("tone_bucket"))

    def undertone_of(s): 
        return _norm(s.get("undertone"))

    # ✅ warm allows olive
    if undertone == "warm":
        undertone_matches = {"warm", "olive"}
    elif undertone:
        undertone_matches = {undertone}
    else:
        undertone_matches = set()

    strict = [
        s for s in shades
        if tone_of(s) == skin_tone and (undertone_of(s) in undertone_matches if undertone_matches else True)
    ]
    tone_only = [s for s in shades if tone_of(s) == skin_tone]
    undertone_only = [s for s in shades if undertone_of(s) in undertone_matches] if undertone_matches else []

    if len(strict) >= k:
        pool = strict
    elif len(tone_only) >= k:
        pool = tone_only
    elif len(undertone_only) >= k:
        pool = undertone_only
    else:
        pool = shades

    # --- photo average color ---
    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    # Slightly upper-center crop to reduce background/chin influence
    crop = img.crop((int(w * 0.38), int(h * 0.28), int(w * 0.62), int(h * 0.55)))
    pixels = list(crop.getdata())

    if not pixels:
        return pool[:k]

    pr = sum(p[0] for p in pixels) / len(pixels)
    pg = sum(p[1] for p in pixels) / len(pixels)
    pb = sum(p[2] for p in pixels) / len(pixels)
    photo_brightness = 0.2126 * pr + 0.7152 * pg + 0.0722 * pb

    # Normalize keys so sample_colors will match even with small spacing/case differences
    normalized_sample = {(_norm(b), _norm(sh)): hx for (b, sh), hx in sample_colors.items()}

    def brightness_guess(shade_obj):
        targets = {"fair": 205, "light": 180, "medium": 145, "tan": 110, "deep": 85}
        return targets.get(tone_of(shade_obj), 145)

    def dist(shade_obj):
        key = (_norm(shade_obj.get("brand")), _norm(shade_obj.get("shade")))
        hx = normalized_sample.get(key)
        rgb = _hex_to_rgb(hx) if hx else None

        if rgb:
            r, g, b = rgb
            return (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2

        # fallback if sample color missing
        return abs(photo_brightness - brightness_guess(shade_obj)) * 1000

    pool_sorted = sorted(pool, key=dist)
    return pool_sorted[:k]

# Makes `is_admin` available in ALL templates automatically
@app.context_processor
def inject_admin_status():
    user = get_current_user()
    return {'is_admin': bool(user and user.get('is_admin'))}


# -------------------------
# AUTH ROUTES
# -------------------------

@app.route('/')
def login_page():
    session.pop('username', None)
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    user = get_user(username)
    if user and user.get('password') == password:
        clear_upload_state()
        session['username'] = username
        return redirect(url_for('profile'))

    flash('Invalid username or password')
    return redirect(url_for('login_page'))


@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/terms-content')
def terms_content():
    return render_template('terms_content.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup_page():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # ✅ required fields now
        email = request.form.get('email', '').strip()
        age_raw = request.form.get('age', '').strip()

        agree_terms = request.form.get('agree_terms')

        if not agree_terms:
            flash("You must agree to the Terms and Conditions to sign up.")
            return redirect(url_for('signup_page'))

        # ✅ require ALL fields
        if not username or not password or not email or not age_raw:
            flash("Please fill out all fields.")
            return redirect(url_for('signup_page'))

        if not age_raw.isdigit():
            flash("Age must be a number.")
            return redirect(url_for('signup_page'))

        age = int(age_raw)
        if age < 1:
            flash("Age must be valid.")
            return redirect(url_for('signup_page'))

        if get_user(username):
            flash("Username already exists.")
            return redirect(url_for('signup_page'))

        create_user(username, password, email, age)
        session['username'] = username
        return redirect(url_for('profile'))

    return render_template('signup.html')




@app.route('/logout')
def logout():
    clear_upload_state()
    session.pop("username", None)
    flash("Logged out.")
    return redirect(url_for('login_page'))



# -------------------------
# PROFILE
# -------------------------

@app.route('/profile')
def profile():
    if 'username' not in session:
        return redirect(url_for('login_page'))

    user = get_current_user()
    if not user:
        return redirect(url_for('login_page'))

    username = user['username']
    is_admin = bool(user.get('is_admin'))

    # ✅ define admin photo ONCE
    ADMIN_PHOTO = '/static/admin.jpg'

    # ✅ ensure admin always uses this photo (optional DB sync)
    if is_admin and user.get('profile_photo') != ADMIN_PHOTO:
        update_profile_photo(username, ADMIN_PHOTO)

    # ✅ choose photo for display
    if is_admin:
        profile_photo_url = ADMIN_PHOTO
    else:
        profile_photo_url = user.get('profile_photo') or '/static/default-profile.png'

    saved_suggestions = []
    if not is_admin:
        saved_suggestions = load_foundation_suggestions(username)

    return render_template(
        'profile.html',
        profile_photo_url=profile_photo_url,
        is_admin=is_admin,
        saved_suggestions=saved_suggestions,
        quiz_answers=session.get("quiz_answers"),
        image_url=session.get("image_url")
    )


@app.route('/set_profile_photo', methods=['POST'])
def set_profile_photo():
    if 'username' not in session:
        return redirect(url_for('login_page'))

    user = get_current_user()
    if not user:
        return redirect(url_for('login_page'))

    username = user['username']
    is_admin = bool(user.get('is_admin'))

    # ✅ block admins from changing profile photo
    if is_admin:
        flash("Admins use the default profile photo.")
        return redirect(url_for('profile'))

    photo = request.form.get('photo', '').strip()

    if not image_belongs_to_user(username, photo):
        flash("Invalid photo selection.")
        return redirect(url_for('profile'))

    update_profile_photo(username, photo)
    flash("Profile photo updated.")
    return redirect(url_for('profile'))

def get_conn():
    """Return a sqlite connection with Row support (dict-like rows)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
# -------------------------
# ADMIN
# -------------------------

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin/feedback')
@admin_required
def admin_feedback():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, username, rating, comment, date
        FROM feedback
        ORDER BY id DESC
    """)
    feedbacks = cursor.fetchall()

    cursor.execute("SELECT AVG(rating) AS avg_rating FROM feedback")
    avg_rating = cursor.fetchone()["avg_rating"]

    cursor.execute("SELECT COUNT(*) AS total FROM feedback")
    total_feedback = cursor.fetchone()["total"]

    conn.close()

    return render_template(
        "admin_feedback.html",
        feedbacks=feedbacks,
        avg_rating=round(avg_rating, 2) if avg_rating else 0,
        total_feedback=total_feedback
    )

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    if 'username' not in session:
        return redirect(url_for('login_page'))

    username = session['username']
    rating = request.form.get('rating')
    comment = request.form.get('comment', '').strip()

    if not rating or not rating.isdigit():
        flash("Please select a rating.")
        return redirect(url_for('profile'))

    rating = int(rating)
    if rating < 1 or rating > 5:
        flash("Invalid rating.")
        return redirect(url_for('profile'))

    if not comment:
        flash("Comment cannot be empty.")
        return redirect(url_for('profile'))

    if len(comment) > 500:
        flash("Comment must be 500 characters only.")
        return redirect(url_for('profile'))

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO feedback (username, rating, comment, date)
        VALUES (?, ?, ?, ?)
    """, (username, rating, comment, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    flash("Thank you for your feedback!")
    return redirect(url_for('profile'))


@app.route('/admin/delete_feedback/<int:feedback_id>', methods=['POST'])
@admin_required
def delete_feedback(feedback_id):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
    conn.commit()
    conn.close()

    flash("Feedback deleted.")
    return redirect(url_for('admin_feedback'))


# -------- USERS --------

@app.route('/admin/users')
@admin_required
def admin_users():
    users = get_all_users()
    return render_template('admin_users.html', users=users)


@app.route('/admin/users/delete', methods=['POST'])
@admin_required
def admin_delete_user():
    username_to_delete = (request.form.get('username') or '').strip()

    if not username_to_delete:
        flash("No user selected.")
        return redirect(url_for('admin_users'))

    # Prevent deleting yourself
    if username_to_delete == session.get('username'):
        flash("You cannot delete your own admin account.")
        return redirect(url_for('admin_users'))

    user_to_delete = get_user(username_to_delete)
    if not user_to_delete:
        flash("User not found.")
        return redirect(url_for('admin_users'))

    # Prevent deleting other admins
    if user_to_delete.get('is_admin'):
        flash("You cannot delete another admin account.")
        return redirect(url_for('admin_users'))

    delete_user(username_to_delete)
    flash(f"Deleted user: {username_to_delete}")
    return redirect(url_for('admin_users'))


# -------- ALL UPLOADS (ADMIN ONLY) --------
# shows photos from: static/uploads/<username>/<file>

@app.route('/admin/all_uploads')
@admin_required
def admin_all_uploads():
    base = app.config['UPLOAD_FOLDER']  # e.g. "static/uploads/"
    all_images = []

    if not os.path.exists(base):
        os.makedirs(base, exist_ok=True)

    for username_folder in os.listdir(base):
        user_dir = os.path.join(base, username_folder)

        if not os.path.isdir(user_dir):
            continue

        for fn in os.listdir(user_dir):
            if fn.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                all_images.append({
                    "username": username_folder,
                    "url": f"/static/uploads/{username_folder}/{fn}"
                })

    # newest-ish first (works better if filenames are uuid-based)
    all_images.sort(key=lambda x: x["url"], reverse=True)

    return render_template("admin_all_uploads.html", images=all_images)


@app.route('/admin/all_uploads/delete', methods=['POST'])
@admin_required
def admin_delete_any_upload():
    photo_url = (request.form.get('photo_url') or '').strip()

    # Must be inside /static/uploads/
    if not photo_url.startswith('/static/uploads/'):
        flash("Invalid photo path.")
        return redirect(url_for('admin_all_uploads'))

    abs_path = os.path.join(app.root_path, photo_url.lstrip('/'))

    if os.path.exists(abs_path):
        os.remove(abs_path)
        flash("Photo deleted.")
    else:
        flash("File not found.")

    return redirect(url_for('admin_all_uploads'))

@app.route('/admin/shades')
@admin_required
def admin_shades():
    shades = load_foundation_shades()

    for s in shades:
        saved = (s.get('sample_color') or '').strip()

        # ✅ Use saved color first
        if saved:
            s['sample_color'] = saved
        else:
            # ✅ Fallback to mapping
            s['sample_color'] = get_sample_color(
                s.get('brand'),
                s.get('shade')
            ) or ""

    return render_template('admin_shades.html', shades=shades)

@app.route('/admin/shades/add', methods=['POST'])
@admin_required
def admin_add_shade():
    brand = request.form.get('brand', '').strip()
    shade_name = request.form.get('shade', '').strip()
    tone_bucket = request.form.get('tone_bucket', '').strip().lower()
    undertone = request.form.get('undertone', '').strip().lower()
    link = request.form.get('link', '').strip()
    sample_color = request.form.get('sample_color', '').strip()

    if not brand or not shade_name:
        flash("Brand and Shade are required.")
        return redirect(url_for('admin_shades'))

    if tone_bucket not in {"fair", "light", "medium", "tan", "deep"}:
        flash("Please select a valid tone bucket.")
        return redirect(url_for('admin_shades'))

    if undertone not in {"warm", "cool", "neutral"}:
        flash("Please select a valid undertone.")
        return redirect(url_for('admin_shades'))

    shades = load_foundation_shades()

    existing_ids = []
    for s in shades:
        try:
            existing_ids.append(int(str(s.get('id'))))
        except:
            pass

    new_id = str((max(existing_ids) + 1) if existing_ids else 1)

    shades.append({
        "id": new_id,
        "brand": brand,
        "shade": shade_name,
        "tone_bucket": tone_bucket,
        "undertone": undertone,
        "link": link,
        "sample_color": sample_color
    })

    save_foundation_shades(shades)
    flash("Shade added.")
    return redirect(url_for('admin_shades'))

@app.route('/admin/shades/update', methods=['POST'])
@admin_required
def admin_update_shade():
    shade_id = request.form.get('id', '').strip()
    brand = request.form.get('brand', '').strip()
    shade_name = request.form.get('shade', '').strip()
    tone_bucket = request.form.get('tone_bucket', '').strip().lower()
    undertone = request.form.get('undertone', '').strip().lower()
    link = request.form.get('link', '').strip()
    sample_color = request.form.get('sample_color', '').strip()

    if not shade_id:
        flash("Missing shade id.")
        return redirect(url_for('admin_shades'))

    if not brand or not shade_name:
        flash("Brand and Shade are required.")
        return redirect(url_for('admin_shades'))

    if tone_bucket not in {"fair", "light", "medium", "tan", "deep"}:
        flash("Please select a valid tone bucket.")
        return redirect(url_for('admin_shades'))

    if undertone not in {"warm", "cool", "neutral"}:
        flash("Please select a valid undertone.")
        return redirect(url_for('admin_shades'))

    shades = load_foundation_shades()
    found = False

    for s in shades:
        if str(s.get('id')) == shade_id:
            s['brand'] = brand
            s['shade'] = shade_name
            s['tone_bucket'] = tone_bucket
            s['undertone'] = undertone
            s['link'] = link
            s['sample_color'] = sample_color
            found = True
            break

    if not found:
        flash("Shade not found.")
        return redirect(url_for('admin_shades'))

    save_foundation_shades(shades)
    flash("Shade updated.")
    return redirect(url_for('admin_shades'))


@app.route('/admin/shades/delete', methods=['POST'])
@admin_required
def admin_delete_shade():
    shade_id = request.form.get('id', '').strip()
    if not shade_id:
        flash("Missing shade id.")
        return redirect(url_for('admin_shades'))

    shades = load_foundation_shades()
    new_shades = [s for s in shades if str(s.get('id')) != shade_id]

    if len(new_shades) == len(shades):
        flash("Shade not found.")
        return redirect(url_for('admin_shades'))

    save_foundation_shades(new_shades)
    flash("Shade deleted.")
    return redirect(url_for('admin_shades'))


# -------------------------
# UPLOAD & ANALYSIS
# -------------------------

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'username' not in session:
        return redirect(url_for('login_page'))

    user = get_current_user()
    if not user:
        return redirect(url_for('login_page'))

    username = user['username']
    is_admin = bool(user.get('is_admin'))

    ensure_user_folder(username)

    uploaded = False
    image_url = session.get('image_url')
    suggestions = None

    # ✅ Only use quiz if it belongs to the currently-logged-in user
    quiz = {}
    if session.get("quiz_owner") == username:
        quiz = session.get("quiz", {}) or {}

    if request.method == 'POST':
        action = request.form.get('action')

        # ----------------
        # UPLOAD IMAGE
        # ----------------
        if action == 'upload':
            if is_admin:
                flash("Admins cannot upload photos here.")
                return redirect(url_for('upload'))

            # ✅ enforce ownership + completeness
            if session.get("quiz_owner") != username:
                flash("Please answer and save the questions first before uploading a photo.")
                return redirect(url_for('upload'))

            quiz = session.get("quiz", {}) or {}
            if not quiz_is_complete(quiz):
                flash("Please answer and save the questions first before uploading a photo.")
                return redirect(url_for('upload'))

            file = request.files.get('photo')
            if not file or not file.filename:
                flash("No file selected.")
                return redirect(url_for('upload'))

            orig = secure_filename(file.filename)
            ext = os.path.splitext(orig)[1].lower()
            filename = f"{uuid4().hex}{ext}"

            filepath = os.path.join(user_upload_folder(username), filename)
            file.save(filepath)

            image_url = safe_user_image_url(username, filename)
            session['image_url'] = image_url
            session['image_path'] = filepath

            uploaded = True

            update_profile_photo(username, image_url)
            flash("Photo uploaded! You can now analyze.")

        # ----------------
        # SAVE QUIZ (USERS ONLY)
        # ----------------
        elif action == 'save_quiz':
            if is_admin:
                flash("Admins cannot answer the questions.")
                return redirect(url_for('upload'))

            quiz = get_quiz_from_form(request.form)

            if not quiz_is_complete(quiz):
                flash("Please answer all 3 questions before saving.")
                return redirect(url_for('upload'))

            # ✅ Bind quiz to the current user
            session["quiz"] = quiz
            session["quiz_owner"] = username

            flash("Answers saved! You can now upload your photo.")
            return redirect(url_for('upload'))

        # ----------------
        # ANALYZE IMAGE (USERS ONLY)
        # ----------------
        elif action == 'analyze':
            if is_admin:
                flash("Admins cannot analyze photos.")
                return redirect(url_for('upload'))

            # ✅ enforce ownership + completeness
            if session.get("quiz_owner") != username:
                flash("Please answer and save the questions first before analyzing your photo.")
                return redirect(url_for('upload'))

            quiz = session.get("quiz", {}) or {}
            if not quiz_is_complete(quiz):
                flash("Please answer and save the questions first before analyzing your photo.")
                return redirect(url_for('upload'))

            filepath = session.get('image_path')
            image_url = session.get('image_url')

            if not image_url:
                flash("Please upload a photo first.")
                return redirect(url_for('upload'))

            if not filepath or not os.path.exists(filepath):
                flash("Uploaded photo not found. Please upload again.")
                return redirect(url_for('upload'))

            suggestions = suggest_shades(filepath, k=2, quiz=quiz)
            uploaded = True

            save_foundation_suggestions(username, suggestions)
            flash("Suggested foundations saved to your profile!")

        else:
            flash("Unknown action.")
            return redirect(url_for('upload'))

    return render_template(
        'upload.html',
        uploaded=uploaded,
        image_url=image_url,
        suggestions=suggestions,
        is_admin=is_admin,
        quiz=quiz
    )


# -------------------------
# BROWSE SHADES
# -------------------------
@app.route('/browse_shades')
def browse_shades():
    if 'username' not in session:
        return redirect(url_for('login_page'))

    foundation_shades = load_foundation_shades()

    for s in foundation_shades:
        saved = (s.get('sample_color') or '').strip()
        s['sample_color'] = saved or (get_sample_color(s.get('brand'), s.get('shade')) or "")
    
    return render_template('browse_shades.html', foundation_shades=foundation_shades)

# -------------------------
# GALLERY
# -------------------------

@app.route('/gallery')
def gallery():
    if 'username' not in session:
        return redirect(url_for('login_page'))

    user = get_current_user()
    if not user:
        return redirect(url_for('login_page'))

    if user.get('is_admin'):
        flash("Admins do not use the user gallery. Use Admin > All Uploads.")
        return redirect(url_for('admin_dashboard'))

    username = user['username']
    ensure_user_folder(username)

    folder = user_upload_folder(username)
    images = [
        safe_user_image_url(username, f)
        for f in os.listdir(folder)
        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
    ]

    return render_template('gallery.html', images=images)


@app.route('/delete_photo', methods=['POST'])
def delete_photo():
    if 'username' not in session:
        return redirect(url_for('login_page'))

    user = get_current_user()
    if not user:
        return redirect(url_for('login_page'))

    if user.get('is_admin'):
        flash("Admins do not have access to user galleries.")
        return redirect(url_for('admin_dashboard'))

    username = user['username']
    photo_path = request.form.get('photo', '').strip()

    prefix = f"/static/uploads/{username}/"
    if not photo_path.startswith(prefix):
        flash("You can only delete your own photos.")
        return redirect(url_for('gallery'))

    abs_path = os.path.join(app.root_path, photo_path.lstrip('/'))
    if os.path.exists(abs_path):
        os.remove(abs_path)
        flash("Photo deleted.")
    else:
        flash("File not found.")

    return redirect(url_for('gallery'))


# -------------------------
# RUN
# -------------------------

if __name__ == '__main__':
    app.run(debug=True)
