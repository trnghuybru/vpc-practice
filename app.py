import os, pymysql
from flask import Flask, render_template, request, redirect, url_for

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER", "quizadmin")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME", "quizdb")

app = Flask(__name__)

def get_conn(db=None):
    return pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASS,
                           database=db, autocommit=True,
                           cursorclass=pymysql.cursors.DictCursor)

def init_db():
    # create database if not exists
    with get_conn(None) as c:
        with c.cursor() as cur:
            cur.execute("CREATE DATABASE IF NOT EXISTS `%s` CHARACTER SET utf8mb4" % DB_NAME)
    with get_conn(DB_NAME) as c:
        with c.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS questions(
                id INT AUTO_INCREMENT PRIMARY KEY,
                question TEXT NOT NULL,
                option_a VARCHAR(255), option_b VARCHAR(255),
                option_c VARCHAR(255), option_d VARCHAR(255),
                correct_option CHAR(1) NOT NULL
            ) ENGINE=InnoDB;
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS attempts(
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100),
                score INT, total INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB;
            """)
            cur.execute("SELECT COUNT(*) AS n FROM questions;")
            if cur.fetchone()["n"] == 0:
                cur.executemany("""
                INSERT INTO questions(question, option_a, option_b, option_c, option_d, correct_option)
                VALUES (%s,%s,%s,%s,%s,%s)
                """, [
                    ("Python web framework phổ biến nào?", "Django", "Rails", "Laravel", "Spring", "A"),
                    ("Cổng mặc định HTTP?", "8080", "80", "443", "21", "B"),
                    ("MySQL port?", "1521", "27017", "5432", "3306", "D"),
                    ("ALB viết tắt của?", "Amazon Linux Build", "Application Load Balancer", "Auto Link Balancer", "App List Base", "B"),
                    ("Lệnh tạo venv Python?", "python -m venv venv", "pip install venv", "virtualenv install", "pyenv create", "A"),
                ])
init_was_run = False

@app.route("/health")
def health():
    return "ok", 200

@app.route("/", methods=["GET", "POST"])
def index():
    global init_was_run
    if not init_was_run:
        init_db(); init_was_run = True
    if request.method == "GET":
        with get_conn(DB_NAME) as c:
            with c.cursor() as cur:
                cur.execute("SELECT id, question, option_a, option_b, option_c, option_d FROM questions ORDER BY RAND() LIMIT 5")
                qs = cur.fetchall()
        return render_template("index.html", questions=qs)
    username = request.form.get("username","Guest")
    answers = {k.split("_")[1]: v for k, v in request.form.items() if k.startswith("q_")}
    ids = list(answers.keys())
    with get_conn(DB_NAME) as c:
        with c.cursor() as cur:
            fmt = ",".join(["%s"]*len(ids))
            cur.execute(f"SELECT id, correct_option FROM questions WHERE id IN ({fmt})", ids)
            key = {str(row["id"]): row["correct_option"] for row in cur.fetchall()}
    score = sum(1 for i, opt in answers.items() if key.get(i)==opt)
    with get_conn(DB_NAME) as c:
        with c.cursor() as cur:
            cur.execute("INSERT INTO attempts(username, score, total) VALUES (%s,%s,%s)", (username, score, len(ids)))
    return redirect(url_for("scores"))

@app.route("/scores")
def scores():
    with get_conn(DB_NAME) as c:
        with c.cursor() as cur:
            cur.execute("SELECT username, score, total, created_at FROM attempts ORDER BY id DESC LIMIT 10")
            rows = cur.fetchall()
    return render_template("scores.html", rows=rows)