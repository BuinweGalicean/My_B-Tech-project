from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import mysql.connector
from mysql.connector import errorcode
import os
import io
import base64
from datetime import datetime
from werkzeug.utils import secure_filename
import logging

try:
    import cv2
except ModuleNotFoundError:
    cv2 = None

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

app = Flask(__name__)
app.secret_key = "secure_voting_system_key_2024"
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'voting_cards'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'biometrics'), exist_ok=True)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_face_recognition_available():
    return cv2 is not None and np is not None

DB_NAME = 'voting_system'

SAMPLE_CANDIDATES = [
    {"name": "Chiroma", "party": "FSNC PARTY", "party_color": "#004085", "image": "chiroma.jpg"},
    {"name": "Kamto", "party": "MRC PARTY", "party_color": "#dc3545", "image": "Kamto.jpg"},
    {"name": "Papi P", "party": "CPDM PARTY", "party_color": "#28a745", "image": "papiP.jpg"}
]

# Database connection
def create_database_if_not_exists():
    try:
        conn = mysql.connector.connect(host="localhost", user="root", password="")
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()
    except mysql.connector.Error as err:
        logger.error(f"Could not create database {DB_NAME}: {err}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database=DB_NAME
        )
        return conn
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_BAD_DB_ERROR:
            logger.info(f"Database {DB_NAME} not found, attempting creation.")
            create_database_if_not_exists()
            try:
                conn = mysql.connector.connect(
                    host="localhost",
                    user="root",
                    password="",
                    database=DB_NAME
                )
                return conn
            except mysql.connector.Error as retry_err:
                logger.error(f"Retry connection error: {retry_err}")
                return None
        logger.error(f"Database connection error: {err}")
        return None

# Initialize database tables
def init_db():
    conn = get_db_connection()
    if not conn:
        logger.error("Could not initialize database")
        return False
    
    cursor = conn.cursor()
    
    try:
        # Create voters table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS voters (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_number VARCHAR(20) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                phone VARCHAR(15) NOT NULL,
                email VARCHAR(100) NOT NULL,
                voting_card_front LONGBLOB,
                voting_card_back LONGBLOB,
                face_data LONGBLOB,
                has_voted BOOLEAN DEFAULT FALSE,
                vote_timestamp TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create candidates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                party VARCHAR(100) NOT NULL,
                party_color VARCHAR(7) NOT NULL,
                image VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Ensure voter table has the expected biometric and card columns
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema=%s AND table_name='voters'
        """, (DB_NAME,))
        voter_columns = {row[0].lower() for row in cursor.fetchall()}

        if 'voting_card_front' not in voter_columns:
            cursor.execute("ALTER TABLE voters ADD COLUMN voting_card_front LONGBLOB")
        if 'voting_card_back' not in voter_columns:
            cursor.execute("ALTER TABLE voters ADD COLUMN voting_card_back LONGBLOB")
        if 'face_data' not in voter_columns:
            cursor.execute("ALTER TABLE voters ADD COLUMN face_data LONGBLOB")
        if 'fingerprint_data' in voter_columns:
            cursor.execute("ALTER TABLE voters DROP COLUMN fingerprint_data")
        if 'has_voted' not in voter_columns:
            cursor.execute("ALTER TABLE voters ADD COLUMN has_voted BOOLEAN DEFAULT FALSE")
        if 'vote_timestamp' not in voter_columns:
            cursor.execute("ALTER TABLE voters ADD COLUMN vote_timestamp TIMESTAMP NULL")

        # Ensure candidate table has the expected schema
        cursor.execute("""
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema=%s AND table_name='candidates'
        """, (DB_NAME,))
        existing_columns = {row[0].lower(): row[1].lower() for row in cursor.fetchall()}

        if 'party_color' not in existing_columns:
            cursor.execute("ALTER TABLE candidates ADD COLUMN party_color VARCHAR(7) NOT NULL DEFAULT '#004085'")

        if 'image' not in existing_columns:
            cursor.execute("ALTER TABLE candidates ADD COLUMN image VARCHAR(255) NULL")
        elif existing_columns.get('image') != 'varchar':
            cursor.execute("ALTER TABLE candidates MODIFY COLUMN image VARCHAR(255)")
        
        # Create votes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                voter_id INT NOT NULL,
                candidate_id INT NOT NULL,
                vote_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (voter_id) REFERENCES voters(id),
                FOREIGN KEY (candidate_id) REFERENCES candidates(id)
            )
        """)
        
        conn.commit()
        logger.info("Database tables initialized successfully")
        return True
    except mysql.connector.Error as err:
        logger.error(f"Error initializing database: {err}")
        return False
    finally:
        cursor.close()
        conn.close()

# Seed sample candidates from static image files
def seed_candidates():
    conn = get_db_connection()
    if not conn:
        return
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name='candidates'", (DB_NAME,))
        existing_columns = {row['column_name'].lower() for row in cursor.fetchall()}
        if 'party_color' not in existing_columns:
            cursor.execute("ALTER TABLE candidates ADD COLUMN party_color VARCHAR(7) NOT NULL DEFAULT '#004085'")
        if 'image' not in existing_columns:
            cursor.execute("ALTER TABLE candidates ADD COLUMN image VARCHAR(255) NULL")

        cursor.execute("SELECT COUNT(*) AS total FROM candidates")
        row = cursor.fetchone()
        sample_candidates = [
            ("Chiroma", "FSNC PARTY", "#004085", "chiroma.jpg"),
            ("Kamto", "MRC PARTY", "#dc3545", "Kamto.jpg"),
            ("Papi P", "CPDM PARTY", "#28a745", "papiP.jpg")
        ]
        if row and row['total'] == 0:
            cursor.executemany(
                "INSERT INTO candidates (name, party, party_color, image) VALUES (%s, %s, %s, %s)",
                sample_candidates
            )
            conn.commit()
        else:
            cursor.execute("SELECT id, name, party, party_color, image FROM candidates")
            existing = {item['name']: item for item in cursor.fetchall()}
            for name, party, color, image in sample_candidates:
                if name in existing:
                    existing_candidate = existing[name]
                    update_needed = (
                        existing_candidate.get('party') != party or
                        existing_candidate.get('party_color') != color or
                        not existing_candidate.get('image') or
                        isinstance(existing_candidate.get('image'), (bytes, bytearray))
                    )
                    if update_needed:
                        cursor.execute(
                            "UPDATE candidates SET party=%s, party_color=%s, image=%s WHERE id=%s",
                            (party, color, image, existing_candidate['id'])
                        )
                else:
                    cursor.execute(
                        "INSERT INTO candidates (name, party, party_color, image) VALUES (%s, %s, %s, %s)",
                        (name, party, color, image)
                    )
            conn.commit()
    except mysql.connector.Error as err:
        logger.error(f"Error seeding candidates: {err}")
    finally:
        cursor.close()
        conn.close()

# Normalize candidate image filenames for templates
def normalize_candidate_images(candidates):
    normalized = []
    for candidate in candidates:
        image_val = candidate.get('image')
        if isinstance(image_val, (bytes, bytearray)):
            try:
                image_val = image_val.decode('utf-8', errors='ignore')
            except Exception:
                image_val = None
        if image_val:
            image_val = image_val.strip()
        if not image_val:
            image_val = 'crm.jpg'
        candidate['image'] = image_val
        normalized.append(candidate)
    return normalized


def get_current_voter():
    voter = None
    if 'voter_id' in session:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT * FROM voters WHERE id=%s", (session['voter_id'],))
                voter = cursor.fetchone()
            except mysql.connector.Error as err:
                logger.error(f"Error loading current voter: {err}")
            finally:
                cursor.close()
                conn.close()
    return voter


def has_biometric_verification(voter):
    # Consider either face or fingerprint data as valid biometric verification
    return bool(voter and (voter.get('face_data') or voter.get('fingerprint_data')))

def has_uploaded_voting_card(voter):
    return bool(voter and voter.get('voting_card_front') and voter.get('voting_card_back'))

def has_identity_verification(voter):
    # Require both a captured biometric (face or fingerprint) and uploaded ID front+back
    return has_biometric_verification(voter) and has_uploaded_voting_card(voter)

def fetch_candidates(retry=True):
    conn = get_db_connection()
    if not conn:
        return normalize_candidate_images([dict(c) for c in SAMPLE_CANDIDATES])
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM candidates ORDER BY id")
        candidates = normalize_candidate_images(cursor.fetchall())
        if not candidates and retry:
            cursor.close()
            conn.close()
            seed_candidates()
            return fetch_candidates(retry=False)
        if not candidates:
            return normalize_candidate_images([dict(c) for c in SAMPLE_CANDIDATES])
        return candidates
    except mysql.connector.Error as err:
        logger.error(f"Error fetching candidates: {err}")
        return normalize_candidate_images([dict(c) for c in SAMPLE_CANDIDATES])
    finally:
        cursor.close()
        conn.close()

# Fetch election results
def fetch_results():
    conn = get_db_connection()
    if not conn:
        return [], None
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT c.id, c.name, c.party, c.party_color, c.image, COUNT(v.id) AS total_votes
            FROM candidates c
            LEFT JOIN votes v ON c.id = v.candidate_id
            GROUP BY c.id
            ORDER BY total_votes DESC
        """)
        results = cursor.fetchall()
        winner = results[0] if results else None
        return results, winner
    except mysql.connector.Error as err:
        logger.error(f"Error fetching results: {err}")
        return [], None
    finally:
        cursor.close()
        conn.close()

# Save a vote in the votes table and update the voter's status
def record_vote(voter_id, candidate_id):
    conn = get_db_connection()
    if not conn:
        return False

    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO votes (voter_id, candidate_id) VALUES (%s, %s)",
            (voter_id, candidate_id)
        )
        cursor.execute(
            "UPDATE voters SET has_voted=TRUE, vote_timestamp=NOW() WHERE id=%s",
            (voter_id,)
        )
        conn.commit()
        return True
    except mysql.connector.Error as err:
        logger.error(f"Error recording vote: {err}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# Save biometric face data for a voter
def save_biometric_data(voter_id, face_data=None):
    conn = get_db_connection()
    if not conn:
        return False

    cursor = conn.cursor()
    try:
        if face_data is not None:
            cursor.execute(
                "UPDATE voters SET face_data=%s WHERE id=%s",
                (face_data, voter_id)
            )
        conn.commit()
        return True
    except mysql.connector.Error as err:
        logger.error(f"Error saving biometric data: {err}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# Verify captured face against the uploaded voting card front image

def is_face_recognition_available():
    return cv2 is not None and np is not None


def load_image_from_bytes(image_bytes):
    if cv2 is None or np is None:
        return None
    try:
        array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            return None
        return image
    except Exception as err:
        logger.error(f"Error decoding image bytes: {err}")
        return None


def detect_face_region(image):
    if cv2 is None:
        return None
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            logger.error("Failed to load Haar cascade for face detection")
            return None
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
        if len(faces) == 0:
            return None
        x, y, w, h = faces[0]
        face = gray[y:y+h, x:x+w]
        face = cv2.resize(face, (200, 200), interpolation=cv2.INTER_AREA)
        return face
    except Exception as err:
        logger.error(f"Error detecting face region: {err}")
        return None


def compare_face_regions(face1, face2):
    if cv2 is None:
        return False, 0
    try:
        orb = cv2.ORB_create(500)
        kp1, des1 = orb.detectAndCompute(face1, None)
        kp2, des2 = orb.detectAndCompute(face2, None)
        if des1 is None or des2 is None or not kp1 or not kp2:
            return False, 0
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        if not matches:
            return False, 0
        good_matches = [m for m in matches if m.distance < 70]
        match_ratio = len(good_matches) / max(1, min(len(kp1), len(kp2)))
        return len(good_matches) >= 8 and match_ratio >= 0.08, len(good_matches)
    except Exception as err:
        logger.error(f"Error comparing face regions: {err}")
        return False, 0


def verify_face_against_voting_card(voter_id, captured_image_bytes):
    if not is_face_recognition_available():
        return False, "Face verification support is not available. Please install requirements and restart the app."
    conn = get_db_connection()
    if not conn:
        return False, "Database connection error"

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT voting_card_front FROM voters WHERE id=%s", (voter_id,))
        row = cursor.fetchone()
        if not row or not row.get('voting_card_front'):
            return False, "Please upload the front of your voting card before scanning your face."

        card_bytes = row['voting_card_front']
        card_face = detect_face_region(load_image_from_bytes(card_bytes))
        if card_face is None:
            return False, "No face was detected on the uploaded voting card. Please upload a clear front image."

        captured_face = detect_face_region(load_image_from_bytes(captured_image_bytes))
        if captured_face is None:
            return False, "No face was detected in the live capture. Please keep your face centered and try again."

        is_match, good_matches = compare_face_regions(card_face, captured_face)
        if is_match:
            return True, f"Face verified successfully ({good_matches} matched features)."
        return False, f"Face did not match the voting card photo ({good_matches} matched features). Please try again."
    except Exception as err:
        logger.error(f"Error verifying face against voting card: {err}")
        return False, "Face verification failed due to a server error."
    finally:
        cursor.close()
        conn.close()


def verify_face_against_registered_face(voter_id, captured_image_bytes):
    if not is_face_recognition_available():
        return False, "Face verification support is not available. Please install requirements and restart the app."

    conn = get_db_connection()
    if not conn:
        return False, "Database connection error"

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT face_data FROM voters WHERE id=%s", (voter_id,))
        row = cursor.fetchone()
        if not row or not row.get('face_data'):
            return False, "No registered face template found. Please register or upload your ID card."

        registered_face_region = detect_face_region(load_image_from_bytes(row['face_data']))
        captured_face_region = detect_face_region(load_image_from_bytes(captured_image_bytes))
        if registered_face_region is None or captured_face_region is None:
            return False, "No face was detected in the registered image or live capture. Please try again."

        is_match, good_matches = compare_face_regions(registered_face_region, captured_face_region)
        if is_match:
            return True, f"Face matched registered identity ({good_matches} matched features)."
        return False, f"Face did not match the registered profile ({good_matches} matched features)."
    except Exception as err:
        logger.error(f"Error verifying face against registered face: {err}")
        return False, "Face verification failed due to a server error."
    finally:
        cursor.close()
        conn.close()

# Route: Registration page (home page)
@app.route("/", methods=["GET", "POST"])
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        id_number = request.form.get("id_number", "").strip()
        first_name = request.form.get("first_name", "").strip()
        middle_name = request.form.get("middle_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        face_image = request.form.get("face_image_data", "").strip()

        name = " ".join(filter(None, [first_name, middle_name, last_name])).strip()

        if not all([id_number, first_name, last_name, phone, email, face_image]):
            flash("All fields and face capture are required for registration.", "error")
            return redirect(url_for("register"))

        if "," in face_image:
            face_image = face_image.split(",", 1)[1]

        try:
            face_bytes = base64.b64decode(face_image, validate=True)
        except Exception:
            try:
                face_bytes = base64.b64decode(face_image)
            except Exception:
                flash("Invalid face image data. Please capture your face again.", "error")
                return redirect(url_for("register"))

        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "error")
            return redirect(url_for("register"))

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id FROM voters WHERE id_number=%s", (id_number,))
            if cursor.fetchone():
                flash("A voter with this ID already exists. Please login instead.", "warning")
                return redirect(url_for("login"))

            cursor.execute(
                "INSERT INTO voters (id_number, name, phone, email, face_data) VALUES (%s, %s, %s, %s, %s)",
                (id_number, name, phone, email, face_bytes)
            )
            conn.commit()
            flash("Registration complete. Please login now.", "success")
            return redirect(url_for("login"))
        except mysql.connector.Error as err:
            logger.error(f"Database error during registration: {err}")
            flash("Registration failed. Please try again.", "error")
            return redirect(url_for("register"))
        finally:
            cursor.close()
            conn.close()

    return render_template(
        "register.html",
        face_module_available=is_face_recognition_available(),
        marquee_text="ÉlectCam — Register to Vote"
    )

# Route: Login page
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Check if user is already voting
        if 'voter_id' in session:
            return redirect(url_for("vote"))

        id_number = request.form.get("id_number", "").strip()
        first_name = request.form.get("first_name", "").strip()
        middle_name = request.form.get("middle_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()

        name = " ".join(filter(None, [first_name, middle_name, last_name])).strip()

        if not all([id_number, first_name, last_name, phone, email]):
            flash("All fields are required!", "error")
            return redirect(url_for("login"))

        conn = get_db_connection()
        if not conn:
            flash("Database connection error", "error")
            return redirect(url_for("login"))

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM voters WHERE id_number=%s", (id_number,))
            voter = cursor.fetchone()

            if voter:
                if voter['has_voted']:
                    flash("You have already voted! Each voter can only vote once.", "error")
                    return redirect(url_for("results"))

                if voter['name'] != name or voter['phone'] != phone or voter['email'] != email:
                    flash("Credentials do not match the registered voter. Please use the same details from registration.", "error")
                    return redirect(url_for("login"))

                session['voter_id'] = voter['id']
                session['voter_id_number'] = id_number
                session.pop('face_verified', None)
            else:
                flash("No registration found for that ID. Please register first.", "warning")
                return redirect(url_for("register"))

            flash("Login successful! Please verify your face to continue.", "success")
            return redirect(url_for("verify"))
        except mysql.connector.Error as err:
            logger.error(f"Database error during login: {err}")
            flash("Login failed. Please try again.", "error")
            return redirect(url_for("login"))
        finally:
            cursor.close()
            conn.close()

    voter = get_current_voter()
    candidates = fetch_candidates()
    results, winner = fetch_results()
    return render_template(
        "login.html",
        candidates=candidates,
        results=results,
        winner=winner,
        voter=voter,
        face_module_available=is_face_recognition_available(),
        marquee_text="ÉlectCam — Voter Login"
    )

@app.route("/verify")
def verify():
    if 'voter_id' not in session:
        flash("Please login first", "warning")
        return redirect(url_for("login"))

    voter = get_current_voter()
    if not voter:
        session.clear()
        flash("Please login again.", "warning")
        return redirect(url_for("login"))

    if session.get('face_verified'):
        return redirect(url_for("vote"))

    return render_template(
        "verify.html",
        voter=voter,
        face_module_available=is_face_recognition_available(),
        marquee_text="ÉlectCam — Face Verification"
    )

# Route: Voting page (biometric verification + voting)
@app.route("/vote", methods=["GET", "POST"])
def vote():
    if 'voter_id' not in session:
        flash("Please login first", "warning")
        return redirect(url_for("login"))

    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "error")
        return redirect(url_for("login"))

    cursor = conn.cursor(dictionary=True)
    try:
        # Get voter info
        cursor.execute("SELECT * FROM voters WHERE id=%s", (session['voter_id'],))
        voter = cursor.fetchone()

        if not voter:
            flash("Voter not found", "error")
            return redirect(url_for("login"))

        if not has_identity_verification(voter):
            flash("Please upload both sides of your ID card and complete biometric verification to confirm your identity before voting.", "warning")
            return redirect(url_for("login"))

        if not session.get('face_verified'):
            flash("Please verify your face before voting.", "warning")
            return redirect(url_for("verify"))

        if voter['has_voted']:
            flash("You have already voted!", "error")
            return redirect(url_for("results"))

        # Get all candidates
        cursor.execute("SELECT * FROM candidates ORDER BY id")
        candidates = cursor.fetchall()

        if request.method == "POST":
            candidate_id = request.form.get("candidate_id") or request.form.get("candidate")

            if not candidate_id:
                flash("Please select a candidate", "warning")
                return render_template("vote.html", candidates=candidates, voter=voter)

            try:
                if not record_vote(session['voter_id'], int(candidate_id)):
                    raise mysql.connector.Error("Vote persistence failed")

                session.clear()
                flash("Vote submitted successfully!", "success")
                return redirect(url_for("results"))
            except mysql.connector.Error as err:
                logger.error(f"Error submitting vote: {err}")
                flash("Error submitting vote. Please try again.", "error")
                return render_template(
                    "vote.html",
                    candidates=candidates,
                    voter=voter,
                    marquee_text="ÉlectCam — Cast Your Vote"
                )

        return render_template(
            "vote.html",
            candidates=candidates,
            voter=voter,
            marquee_text="ÉlectCam — Cast Your Vote"
        )

    except mysql.connector.Error as err:
        logger.error(f"Database error in voting: {err}")
        flash("Database error", "error")
        return redirect(url_for("login"))
    finally:
        cursor.close()
        conn.close()

# Route: Capture voting card
@app.route("/upload-voting-card", methods=["POST"])
def upload_voting_card():
    if 'voter_id' not in session:
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    
    try:
        card_side = request.form.get("side")  # 'front' or 'back'
        file = request.files.get("file")
        
        if not file or not card_side:
            return jsonify({"success": False, "message": "Missing file or side"}), 400
        
        filename = secure_filename(f"card_{session['voter_id']}_{card_side}_{datetime.now().timestamp()}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'voting_cards', filename)
        
        # Read file content
        file_content = file.read()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update database
        if card_side == "front":
            cursor.execute(
                "UPDATE voters SET voting_card_front=%s WHERE id=%s",
                (file_content, session['voter_id'])
            )
        else:
            cursor.execute(
                "UPDATE voters SET voting_card_back=%s WHERE id=%s",
                (file_content, session['voter_id'])
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": f"{card_side.capitalize()} card uploaded"}), 200
    
    except Exception as e:
        logger.error(f"Error uploading card: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

# Route: Capture biometric (face)
@app.route("/capture-face", methods=["POST"])
def capture_face():
    if 'voter_id' not in session:
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    
    if not is_face_recognition_available():
        return jsonify({"success": False, "message": "Face verification support is not available. Please install requirements and restart the app."}), 500

    try:
        data = request.get_json()
        image_data = data.get("image_data") if isinstance(data, dict) else None
        
        if not image_data:
            return jsonify({"success": False, "message": "No image data"}), 400
        
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        try:
            image_binary = base64.b64decode(image_data, validate=True)
        except Exception:
            image_binary = base64.b64decode(image_data)

        voter = get_current_voter()
        if not voter:
            return jsonify({"success": False, "message": "Voter session invalid"}), 401

        if voter.get('face_data'):
            success, message = verify_face_against_registered_face(voter['id'], image_binary)
        elif voter.get('voting_card_front'):
            success, message = verify_face_against_voting_card(voter['id'], image_binary)
        else:
            return jsonify({"success": False, "message": "No reference face template or voting card available for verification."}), 400

        if not success:
            return jsonify({"success": False, "message": message}), 400

        if not voter.get('face_data'):
            if not save_biometric_data(voter['id'], face_data=image_binary):
                logger.error("Unable to save biometric face data for voter_id=%s", voter['id'])
                return jsonify({"success": False, "message": "Failed to save face data"}), 500

        session['face_verified'] = True

        conn = get_db_connection()
        has_voted = False
        if conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT has_voted FROM voters WHERE id=%s", (voter['id'],))
                row = cursor.fetchone()
                has_voted = bool(row and row.get('has_voted'))
            except mysql.connector.Error as err:
                logger.error(f"Error checking vote status after face capture: {err}")
            finally:
                cursor.close()
                conn.close()

        redirect_url = url_for('results') if has_voted else url_for('vote')
        return jsonify({"success": True, "message": message, "redirect": redirect_url}), 200
    
    except Exception as e:
        logger.error(f"Error capturing face: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Failed to capture face data"}), 500

# Route: Results page
@app.route("/results")
def results():
    conn = get_db_connection()
    if not conn:
        flash("Database connection error", "error")
        return redirect(url_for("login"))
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get vote counts
        cursor.execute("""
            SELECT c.id, c.name, c.party, c.party_color, COUNT(v.id) AS total_votes
            FROM candidates c
            LEFT JOIN votes v ON c.id = v.candidate_id
            GROUP BY c.id
            ORDER BY total_votes DESC
        """)
        
        results = cursor.fetchall()
        
        # Determine winner
        winner = results[0] if results else None
        
        # Get total votes
        total_votes = sum(r['total_votes'] for r in results)
        
        cursor.close()
        conn.close()
        
        return render_template("results.html", results=results, winner=winner, total_votes=total_votes)
    
    except mysql.connector.Error as err:
        logger.error(f"Error fetching results: {err}")
        flash("Error fetching results", "error")
        return redirect(url_for("login"))
    finally:
        cursor.close()
        conn.close()

# Route: Results API (for chart)
@app.route("/api/results")
def results_api():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT c.name, c.party, c.party_color, COUNT(v.id) AS votes
            FROM candidates c
            LEFT JOIN votes v ON c.id = v.candidate_id
            GROUP BY c.id
            ORDER BY votes DESC
        """)
        
        data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(data)
    
    except mysql.connector.Error as err:
        logger.error(f"Error in results API: {err}")
        return jsonify({"error": "Database error"}), 500
    finally:
        cursor.close()
        conn.close()

# Route: Logout
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for("login"))

# Route: Health check
@app.route("/health")
def health():
    conn = get_db_connection()
    if conn:
        conn.close()
        return jsonify({"status": "healthy"}), 200
    else:
        return jsonify({"status": "unhealthy"}), 500

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", message="Page not found"), 404

@app.errorhandler(500)
def server_error(error):
    return render_template("error.html", message="Server error"), 500

if __name__ == "__main__":
    # Initialize database tables and seed candidates
    if init_db():
        seed_candidates()
    
    # Run the app
    app.run(debug=True, host="localhost", port=5000)