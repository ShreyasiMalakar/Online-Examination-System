from flask import Flask, render_template, request, redirect, flash, session, jsonify
import mysql.connector
import random
import json
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"

# MySQL connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",   # default in XAMPP
    database="app_db"
)

cursor = db.cursor()

# ---------------- HOME ----------------
@app.route('/')
def home():
    return redirect('/login')

# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        # Check if user already exists
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash("Email already registered!")
            return redirect('/register')

        # Hash password
        hashed_password = generate_password_hash(password)

        # Insert into DB
        cursor.execute(
            "INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)",
            (username, email, hashed_password, role)
        )
        db.commit()

        flash("Registration successful! Please login.")
        return redirect('/login')

    return render_template('register.html')

# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['role'] = user[4]
            session['username'] = user[1]

            flash("Login successful!")

            if user[4] == 'student':
                return redirect('/student_dashboard')
            else:
                return redirect('/teacher_dashboard')
        else:
            flash("Invalid username or password!")

    return render_template('login.html')

# ---------------- STUDENT DASHBOARD ----------------
@app.route('/student_dashboard')
def student_dashboard():
    if 'role' in session and session['role'] == 'student':
        uid = session['user_id']

        # --- Stats cards ---
        cursor.execute("SELECT COUNT(*) FROM results WHERE student_id=%s", (uid,))
        total_tests = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(score/total*100) FROM results WHERE student_id=%s", (uid,))
        avg_score_row = cursor.fetchone()[0]
        avg_score = round(float(avg_score_row), 1) if avg_score_row else 0

        cursor.execute("""
            SELECT subject, AVG(score/total*100) as avg_pct FROM results
            WHERE student_id=%s GROUP BY subject ORDER BY avg_pct DESC LIMIT 1
        """, (uid,))
        best_subject_row = cursor.fetchone()
        best_subject = best_subject_row[0] if best_subject_row else 'N/A'

        cursor.execute("SELECT MAX(score) FROM results WHERE student_id=%s", (uid,))
        highest_score_row = cursor.fetchone()[0]
        highest_score = int(highest_score_row) if highest_score_row else 0

        # --- Performance trend (last 10 tests) ---
        cursor.execute("""
            SELECT subject, score, total, DATE_FORMAT(date, '%%d %%b') as label
            FROM results WHERE student_id=%s ORDER BY date DESC LIMIT 10
        """, (uid,))
        trend_raw = cursor.fetchall()
        trend_labels = [r[3] for r in reversed(trend_raw)]
        trend_scores = [round(float(r[1])/float(r[2])*100, 1) if r[2] else 0 for r in reversed(trend_raw)]

        # --- Subject-wise avg (radar chart) ---
        cursor.execute("""
            SELECT subject, AVG(score/total*100) as avg_pct
            FROM results WHERE student_id=%s GROUP BY subject
        """, (uid,))
        subj_raw = cursor.fetchall()
        subj_labels = [r[0] for r in subj_raw]
        subj_scores = [round(float(r[1]), 1) for r in subj_raw]

        # --- Score distribution (doughnut) ---
        cursor.execute("""
            SELECT
                SUM(CASE WHEN score/total*100 >= 80 THEN 1 ELSE 0 END) as excellent,
                SUM(CASE WHEN score/total*100 >= 60 AND score/total*100 < 80 THEN 1 ELSE 0 END) as good,
                SUM(CASE WHEN score/total*100 >= 40 AND score/total*100 < 60 THEN 1 ELSE 0 END) as average,
                SUM(CASE WHEN score/total*100 < 40 THEN 1 ELSE 0 END) as poor
            FROM results WHERE student_id=%s
        """, (uid,))
        dist_row = cursor.fetchone()
        score_dist = [int(d or 0) for d in dist_row] if dist_row else [0,0,0,0]

        # --- Recent results ---
        cursor.execute("""
            SELECT subject, score, total, DATE_FORMAT(date, '%%d %%b %%Y') as label
            FROM results WHERE student_id=%s ORDER BY date DESC LIMIT 5
        """, (uid,))
        recent_results_raw = cursor.fetchall()
        recent_results = [(r[0], int(r[1]), int(r[2]), r[3]) for r in recent_results_raw]

        return render_template('student_dashboard.html',
            name=session['username'],
            total_tests=total_tests,
            avg_score=avg_score,
            best_subject=best_subject,
            highest_score=highest_score,
            trend_labels=json.dumps(trend_labels),
            trend_scores=json.dumps(trend_scores),
            subj_labels=json.dumps(subj_labels),
            subj_scores=json.dumps(subj_scores),
            score_dist=json.dumps(score_dist),
            recent_results=recent_results
        )
    else:
        return redirect('/login')

# ---------------- TEACHER DASHBOARD ----------------
@app.route('/teacher_dashboard')
def teacher_dashboard():
    if 'role' in session and session['role'] == 'teacher':

        # --- Stats ---
        cursor.execute("SELECT COUNT(*) FROM users WHERE role='student'")
        total_students = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM questions")
        total_questions = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM results")
        total_submissions = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(score/total*100) FROM results")
        class_avg_row = cursor.fetchone()[0]
        class_avg = round(float(class_avg_row), 1) if class_avg_row else 0

        # --- Subject-wise class average (bar chart) ---
        cursor.execute("""
            SELECT subject, AVG(score/total*100) as avg_pct
            FROM results GROUP BY subject
        """)
        subj_raw = cursor.fetchall()
        subj_labels = [r[0] for r in subj_raw]
        subj_avgs = [round(float(r[1]), 1) for r in subj_raw]

        # --- Score distribution across all students ---
        cursor.execute("""
            SELECT
                SUM(CASE WHEN score/total*100 >= 80 THEN 1 ELSE 0 END),
                SUM(CASE WHEN score/total*100 >= 60 AND score/total*100 < 80 THEN 1 ELSE 0 END),
                SUM(CASE WHEN score/total*100 >= 40 AND score/total*100 < 60 THEN 1 ELSE 0 END),
                SUM(CASE WHEN score/total*100 < 40 THEN 1 ELSE 0 END)
            FROM results
        """)
        dist_row = cursor.fetchone()
        score_dist = [int(d or 0) for d in dist_row] if dist_row else [0,0,0,0]

        # --- Top 5 performers ---
        cursor.execute("""
            SELECT u.username, AVG(r.score/r.total*100) as avg_pct, COUNT(*) as tests_taken
            FROM results r JOIN users u ON r.student_id = u.id
            GROUP BY u.username ORDER BY avg_pct DESC LIMIT 5
        """)
        top_performers_raw = cursor.fetchall()
        top_performers = [(r[0], float(r[1]), int(r[2])) for r in top_performers_raw]

        # --- Tests per subject (pie chart) ---
        cursor.execute("""
            SELECT subject, COUNT(*) as cnt FROM results GROUP BY subject
        """)
        tests_per_subj_raw = cursor.fetchall()
        tests_subj_labels = [r[0] for r in tests_per_subj_raw]
        tests_subj_counts = [int(r[1]) for r in tests_per_subj_raw]

        # --- Recent submissions ---
        cursor.execute("""
            SELECT u.username, r.subject, r.score, r.total, DATE_FORMAT(r.date, '%d %b %Y') as label
            FROM results r JOIN users u ON r.student_id = u.id
            ORDER BY r.date DESC LIMIT 8
        """)
        recent_submissions_raw = cursor.fetchall()
        recent_submissions = [(r[0], r[1], int(r[2]), int(r[3]), r[4]) for r in recent_submissions_raw]

        # --- Monthly submissions trend ---
        cursor.execute("""
            SELECT DATE_FORMAT(date, '%b %Y') as month_label, COUNT(*) as cnt
            FROM results GROUP BY month_label ORDER BY MIN(date) DESC LIMIT 6
        """)
        monthly_raw = cursor.fetchall()
        monthly_labels = [r[0] for r in reversed(monthly_raw)]
        monthly_counts = [int(r[1]) for r in reversed(monthly_raw)]

        return render_template('teacher_dashboard.html',
            name=session['username'],
            total_students=total_students,
            total_questions=total_questions,
            total_submissions=total_submissions,
            class_avg=class_avg,
            subj_labels=json.dumps(subj_labels),
            subj_avgs=json.dumps(subj_avgs),
            score_dist=json.dumps(score_dist),
            top_performers=top_performers,
            tests_subj_labels=json.dumps(tests_subj_labels),
            tests_subj_counts=json.dumps(tests_subj_counts),
            recent_submissions=recent_submissions,
            monthly_labels=json.dumps(monthly_labels),
            monthly_counts=json.dumps(monthly_counts)
        )
    else:
        return redirect('/login')

# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully!")
    return redirect('/login')

@app.route('/results')
def results():
    cursor.execute(
        "SELECT score, total, date FROM results WHERE student_id=%s ORDER BY date DESC",
        (session['user_id'],)
    )
    data = cursor.fetchall()

    return render_template("view_results.html", results=data)


@app.route('/all_results')
def all_results():
    if 'role' in session and session['role'] == 'teacher':
        cursor.execute("""
            SELECT u.username, r.subject, r.score, r.total, r.date 
            FROM results r
            JOIN users u ON r.student_id = u.id
            ORDER BY r.date DESC
        """)
        results = cursor.fetchall()
        return render_template('all_results.html', results=results)
    else:
        return redirect('/login')


@app.route('/take_test_subject/<subject>')
def take_test_subject(subject):

    import random   # 👈 add this

    # Get all questions of that subject
    cursor.execute(
        "SELECT * FROM questions WHERE subject=%s",
        (subject,)
    )
    all_questions = cursor.fetchall()

    # Pick only 10 random questions
    questions = random.sample(all_questions, min(10, len(all_questions)))

    return render_template('take_test.html', questions=questions, subject=subject)


@app.route('/submit_test', methods=['POST'])
def submit_test():
    score = 0

    # 👇 GET SUBJECT PROPERLY
    subject = request.form.get('subject')
    print("SUBJECT RECEIVED:", subject)  # DEBUG

    question_ids = request.form['question_ids'].split(',')
    question_ids = [q for q in question_ids if q]

    for qid in question_ids:
        cursor.execute(
            "SELECT correct_option FROM questions WHERE id=%s",
            (qid,)
        )
        correct = str(cursor.fetchone()[0])

        user_ans = request.form.get(qid)

        if user_ans == correct:
            score += 1

    total = len(question_ids)

    # 👇 INSERT WITH SUBJECT (VERY IMPORTANT)
    cursor.execute(
        "INSERT INTO results (student_id, score, total, subject) VALUES (%s, %s, %s, %s)",
        (session['user_id'], score, total, subject)
    )
    db.commit()

    return render_template("result.html", score=score, total=total)


@app.route('/create_question', methods=['GET', 'POST'])
def create_question():
    if request.method == 'POST':
        subject = request.form['subject']
        q = request.form['question']
        o1 = request.form['o1']
        o2 = request.form['o2']
        o3 = request.form['o3']
        o4 = request.form['o4']
        correct = request.form['correct']

        cursor.execute(
            "INSERT INTO questions (question, option1, option2, option3, option4, correct_option, created_by, subject) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (q, o1, o2, o3, o4, correct, session['user_id'], subject)
        )
        db.commit()

        return "Question Added Successfully!"

    return render_template('create_test.html')

@app.route('/create_test_name', methods=['GET', 'POST'])
def create_test_name():
    if request.method == 'POST':
        title = request.form['title']

        cursor.execute(
            "INSERT INTO tests (title, created_by) VALUES (%s, %s)",
            (title, session['user_id'])
        )
        db.commit()

        return "Test Created!"

    return render_template('create_test_name.html')

@app.route('/select_test')
def select_test():
    cursor.execute("SELECT * FROM tests")
    tests = cursor.fetchall()

    return render_template('select_test.html', tests=tests)

@app.route('/select_subject')
def select_subject():
    cursor.execute("SELECT DISTINCT subject FROM questions")
    subjects = cursor.fetchall()

    return render_template('select_subject.html', subjects=subjects)


@app.route('/leaderboard')
def leaderboard():

    cursor.execute("""
        SELECT u.username, r.score, r.total, r.subject
        FROM results r
        JOIN users u ON r.student_id = u.id
        JOIN (
            SELECT student_id, subject, MIN(date) as first_attempt
            FROM results
            GROUP BY student_id, subject
        ) first_res ON r.student_id = first_res.student_id 
        AND r.subject = first_res.subject 
        AND r.date = first_res.first_attempt
        ORDER BY (r.score / r.total) DESC
        LIMIT 10
    """)

    data = cursor.fetchall()

    return render_template("leaderboard.html", data=data)

# ---------------- STUDY MATERIALS ----------------
@app.route('/study_materials')
def study_materials():
    if 'role' in session and session['role'] == 'student':
        # In a real app, this might query a database
        materials = [
            {"title": "Introduction to Python", "type": "PDF", "size": "2.4 MB", "icon": "bi-file-earmark-pdf text-danger"},
            {"title": "Advanced Database Management", "type": "Video", "size": "150 MB", "icon": "bi-file-earmark-play text-primary"},
            {"title": "Operating Systems Architecture", "type": "Notes", "size": "1.1 MB", "icon": "bi-file-earmark-text text-success"},
            {"title": "Computer Networks Revision", "type": "PDF", "size": "3.5 MB", "icon": "bi-file-earmark-pdf text-danger"}
        ]
        return render_template('study_materials.html', materials=materials)
    else:
        return redirect('/login')

# ---------------- MANAGE QUESTIONS ----------------
@app.route('/manage_questions')
def manage_questions():
    if 'role' in session and session['role'] == 'teacher':
        cursor.execute("SELECT id, subject, question, correct_option FROM questions WHERE created_by=%s", (session['user_id'],))
        questions = cursor.fetchall()
        return render_template('manage_questions.html', questions=questions)
    else:
        return redirect('/login')

# ---------------- RUN ----------------
if __name__ == '__main__':
    app.run(debug=True)