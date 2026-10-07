from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

DATABASE = "database.db"


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS voters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voter_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            has_voted INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            party TEXT NOT NULL,
            symbol TEXT NOT NULL,
            description TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voter_id INTEGER UNIQUE NOT NULL,
            candidate_id INTEGER NOT NULL,
            voted_at TEXT NOT NULL,
            FOREIGN KEY(voter_id) REFERENCES voters(id),
            FOREIGN KEY(candidate_id) REFERENCES candidates(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            election_open INTEGER DEFAULT 1
        )
    """)

    admin = conn.execute(
        "SELECT * FROM admin WHERE username = ?",
        ("admin",)
    ).fetchone()

    if not admin:
        conn.execute(
            "INSERT INTO admin (username, password) VALUES (?, ?)",
            ("admin", generate_password_hash("admin123"))
        )

    setting = conn.execute(
        "SELECT * FROM settings WHERE id = 1"
    ).fetchone()

    if not setting:
        conn.execute(
            "INSERT INTO settings (id, election_open) VALUES (1, 1)"
        )

    candidate_count = conn.execute(
        "SELECT COUNT(*) FROM candidates"
    ).fetchone()[0]

    if candidate_count == 0:
        sample_candidates = [
            ("Rahul Patil", "Progressive Party", "🌳",
             "Focused on education and employment."),
            ("Amit Sharma", "Development Party", "⭐",
             "Focused on technology and infrastructure."),
            ("Sneha Joshi", "People's Party", "🌸",
             "Focused on social development and welfare.")
        ]

        conn.executemany("""
            INSERT INTO candidates
            (name, party, symbol, description)
            VALUES (?, ?, ?, ?)
        """, sample_candidates)

    conn.commit()
    conn.close()


# ---------------- HELPERS ----------------

def voter_login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "voter_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper


def admin_login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "admin_id" not in session:
            flash("Admin login required.", "warning")
            return redirect(url_for("admin_login"))
        return func(*args, **kwargs)

    return wrapper


def election_is_open():
    conn = get_db()
    setting = conn.execute(
        "SELECT election_open FROM settings WHERE id = 1"
    ).fetchone()
    conn.close()

    return bool(setting["election_open"])


# ---------------- HOME ----------------

@app.route("/")
def index():
    conn = get_db()

    candidate_count = conn.execute(
        "SELECT COUNT(*) FROM candidates"
    ).fetchone()[0]

    voter_count = conn.execute(
        "SELECT COUNT(*) FROM voters"
    ).fetchone()[0]

    vote_count = conn.execute(
        "SELECT COUNT(*) FROM votes"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        candidate_count=candidate_count,
        voter_count=voter_count,
        vote_count=vote_count,
        election_open=election_is_open()
    )


# ---------------- VOTER REGISTRATION ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        voter_id = request.form["voter_id"].strip()
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not voter_id or not name or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return redirect(url_for("register"))

        conn = get_db()

        try:
            conn.execute("""
                INSERT INTO voters
                (voter_id, name, email, password, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                voter_id,
                name,
                email,
                generate_password_hash(password),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

            conn.commit()

            flash("Registration successful. Please login.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Voter ID or email already registered.", "danger")

        finally:
            conn.close()

    return render_template("register.html")


# ---------------- VOTER LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        voter_id = request.form["voter_id"]
        password = request.form["password"]

        conn = get_db()

        voter = conn.execute(
            "SELECT * FROM voters WHERE voter_id = ?",
            (voter_id,)
        ).fetchone()

        conn.close()

        if voter and check_password_hash(voter["password"], password):

            session.clear()
            session["voter_id"] = voter["id"]
            session["voter_name"] = voter["name"]

            return redirect(url_for("voter_dashboard"))

        flash("Invalid voter ID or password.", "danger")

    return render_template("login.html")


# ---------------- VOTER DASHBOARD ----------------

@app.route("/dashboard")
@voter_login_required
def voter_dashboard():

    conn = get_db()

    voter = conn.execute(
        "SELECT * FROM voters WHERE id = ?",
        (session["voter_id"],)
    ).fetchone()

    conn.close()

    return render_template(
        "voter_dashboard.html",
        voter=voter,
        election_open=election_is_open()
    )


# ---------------- VOTE ----------------

@app.route("/vote")
@voter_login_required
def vote():

    if not election_is_open():
        flash("Voting is currently closed.", "warning")
        return redirect(url_for("voter_dashboard"))

    conn = get_db()

    voter = conn.execute(
        "SELECT * FROM voters WHERE id = ?",
        (session["voter_id"],)
    ).fetchone()

    candidates = conn.execute(
        "SELECT * FROM candidates ORDER BY id"
    ).fetchall()

    conn.close()

    if voter["has_voted"]:
        flash("You have already voted.", "info")
        return redirect(url_for("confirmation"))

    return render_template(
        "vote.html",
        candidates=candidates
    )


# ---------------- CAST VOTE ----------------

@app.route("/cast-vote", methods=["POST"])
@voter_login_required
def cast_vote():

    if not election_is_open():
        flash("Voting is currently closed.", "warning")
        return redirect(url_for("voter_dashboard"))

    candidate_id = request.form.get("candidate_id")

    if not candidate_id:
        flash("Please select a candidate.", "danger")
        return redirect(url_for("vote"))

    conn = get_db()

    voter = conn.execute(
        "SELECT * FROM voters WHERE id = ?",
        (session["voter_id"],)
    ).fetchone()

    if voter["has_voted"]:
        conn.close()
        flash("You have already voted.", "warning")
        return redirect(url_for("confirmation"))

    candidate = conn.execute(
        "SELECT * FROM candidates WHERE id = ?",
        (candidate_id,)
    ).fetchone()

    if not candidate:
        conn.close()
        flash("Invalid candidate.", "danger")
        return redirect(url_for("vote"))

    try:

        conn.execute("""
            INSERT INTO votes
            (voter_id, candidate_id, voted_at)
            VALUES (?, ?, ?)
        """, (
            session["voter_id"],
            candidate_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.execute("""
            UPDATE voters
            SET has_voted = 1
            WHERE id = ?
        """, (session["voter_id"],))

        conn.commit()

    except sqlite3.IntegrityError:
        conn.rollback()
        flash("Vote could not be recorded.", "danger")
        conn.close()
        return redirect(url_for("vote"))

    conn.close()

    return redirect(url_for("confirmation"))


# ---------------- CONFIRMATION ----------------

@app.route("/confirmation")
@voter_login_required
def confirmation():

    conn = get_db()

    vote = conn.execute("""
        SELECT candidates.name, candidates.party,
               candidates.symbol, votes.voted_at
        FROM votes
        JOIN candidates
        ON votes.candidate_id = candidates.id
        WHERE votes.voter_id = ?
    """, (session["voter_id"],)).fetchone()

    conn.close()

    return render_template(
        "confirmation.html",
        vote=vote
    )


# ---------------- RESULTS ----------------

@app.route("/results")
def results():

    conn = get_db()

    results = conn.execute("""
        SELECT candidates.name,
               candidates.party,
               candidates.symbol,
               COUNT(votes.id) AS vote_count
        FROM candidates
        LEFT JOIN votes
        ON candidates.id = votes.candidate_id
        GROUP BY candidates.id
        ORDER BY vote_count DESC
    """).fetchall()

    total_votes = conn.execute(
        "SELECT COUNT(*) FROM votes"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "results.html",
        results=results,
        total_votes=total_votes
    )


# ---------------- ADMIN LOGIN ----------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()

        admin = conn.execute(
            "SELECT * FROM admin WHERE username = ?",
            (username,)
        ).fetchone()

        conn.close()

        if admin and check_password_hash(
            admin["password"],
            password
        ):

            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]

            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin credentials.", "danger")

    return render_template("admin/login.html")


# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin/dashboard")
@admin_login_required
def admin_dashboard():

    conn = get_db()

    voters = conn.execute(
        "SELECT COUNT(*) FROM voters"
    ).fetchone()[0]

    candidates = conn.execute(
        "SELECT COUNT(*) FROM candidates"
    ).fetchone()[0]

    votes = conn.execute(
        "SELECT COUNT(*) FROM votes"
    ).fetchone()[0]

    voted_voters = conn.execute(
        "SELECT COUNT(*) FROM voters WHERE has_voted = 1"
    ).fetchone()[0]

    conn.close()

    percentage = 0

    if voters > 0:
        percentage = round((votes / voters) * 100, 2)

    return render_template(
        "admin/dashboard.html",
        voters=voters,
        candidates=candidates,
        votes=votes,
        voted_voters=voted_voters,
        percentage=percentage,
        election_open=election_is_open()
    )


# ---------------- CANDIDATES ----------------

@app.route("/admin/candidates", methods=["GET", "POST"])
@admin_login_required
def admin_candidates():

    conn = get_db()

    if request.method == "POST":

        name = request.form["name"].strip()
        party = request.form["party"].strip()
        symbol = request.form["symbol"].strip()
        description = request.form["description"].strip()

        if name and party and symbol:

            conn.execute("""
                INSERT INTO candidates
                (name, party, symbol, description)
                VALUES (?, ?, ?, ?)
            """, (
                name,
                party,
                symbol,
                description
            ))

            conn.commit()

            flash("Candidate added successfully.", "success")

    candidates = conn.execute(
        "SELECT * FROM candidates ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "admin/candidates.html",
        candidates=candidates
    )


@app.route("/admin/candidates/delete/<int:candidate_id>")
@admin_login_required
def delete_candidate(candidate_id):

    conn = get_db()

    used = conn.execute(
        "SELECT COUNT(*) FROM votes WHERE candidate_id = ?",
        (candidate_id,)
    ).fetchone()[0]

    if used > 0:
        flash("Candidate cannot be deleted after receiving votes.", "warning")
    else:
        conn.execute(
            "DELETE FROM candidates WHERE id = ?",
            (candidate_id,)
        )

        conn.commit()

        flash("Candidate deleted.", "success")

    conn.close()

    return redirect(url_for("admin_candidates"))


# ---------------- VOTERS ----------------

@app.route("/admin/voters")
@admin_login_required
def admin_voters():

    conn = get_db()

    voters = conn.execute("""
        SELECT id, voter_id, name, email,
               has_voted, created_at
        FROM voters
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin/voters.html",
        voters=voters
    )


# ---------------- ADMIN RESULTS ----------------

@app.route("/admin/results")
@admin_login_required
def admin_results():

    conn = get_db()

    results = conn.execute("""
        SELECT candidates.name,
               candidates.party,
               candidates.symbol,
               COUNT(votes.id) AS vote_count
        FROM candidates
        LEFT JOIN votes
        ON candidates.id = votes.candidate_id
        GROUP BY candidates.id
        ORDER BY vote_count DESC
    """).fetchall()

    total_votes = conn.execute(
        "SELECT COUNT(*) FROM votes"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "admin/results.html",
        results=results,
        total_votes=total_votes
    )


# ---------------- ELECTION CONTROL ----------------

@app.route("/admin/toggle-election")
@admin_login_required
def toggle_election():

    conn = get_db()

    current = conn.execute(
        "SELECT election_open FROM settings WHERE id = 1"
    ).fetchone()["election_open"]

    new_status = 0 if current else 1

    conn.execute("""
        UPDATE settings
        SET election_open = ?
        WHERE id = 1
    """, (new_status,))

    conn.commit()
    conn.close()

    flash(
        "Election status updated successfully.",
        "success"
    )

    return redirect(url_for("admin_dashboard"))


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("index"))


# ---------------- RUN ----------------

if __name__ == "__main__":
    init_db()

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )