# app.py
import os
import pymysql
from flask import Flask, render_template, request, redirect, url_for, abort

# ====== Config từ ENV ======
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER", "quizadmin")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME", "quizdb")

app = Flask(__name__)

# ====== Helper: mở kết nối MySQL ======
def get_conn(db=None):
    if not DB_HOST or not DB_PASS:
        # Cho phép app vẫn sống để /health trả 200, nhưng báo rõ khi cần DB
        raise RuntimeError("Database env is not configured (DB_HOST/DB_PASS).")
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=db,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        read_timeout=5,
        write_timeout=5,
        charset="utf8mb4",
    )

# ====== Init DB (idempotent) ======
def init_db():
    # Tạo database nếu chưa có
    with get_conn(None) as c:
        with c.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4")
    # Tạo bảng & seed dữ liệu nếu trống
    with get_conn(DB_NAME) as c:
        with c.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS questions(
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    question TEXT NOT NULL,
                    option_a VARCHAR(255), option_b VARCHAR(255),
                    option_c VARCHAR(255), option_d VARCHAR(255),
                    correct_option CHAR(1) NOT NULL
                ) ENGINE=InnoDB;
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS attempts(
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100),
                    score INT, total INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB;
                """
            )
            cur.execute("SELECT COUNT(*) AS n FROM questions;")
            if cur.fetchone()["n"] == 0:
                cur.executemany(
                    """
                    INSERT INTO questions
                      (question, option_a, option_b, option_c, option_d, correct_option)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    [
                        ("Python web framework phổ biến nào?", "Django", "Rails", "Laravel", "Spring", "A"),
                        ("Cổng mặc định HTTP?", "8080", "80", "443", "21", "B"),
                        ("MySQL port?", "1521", "27017", "5432", "3306", "D"),
                        ("ALB viết tắt của?", "Amazon Linux Build", "Application Load Balancer", "Auto Link Balancer", "App List Base", "B"),
                        ("Lệnh tạo venv Python?", "python -m venv venv", "pip install venv", "virtualenv install", "pyenv create", "A"),
                    ],
                )

# Khởi tạo DB khi có request đầu tiên (mỗi worker của Gunicorn sẽ chạy 1 lần)
@app.before_first_request
def _before_first_request():
    try:
        init_db()
    except Exception as e:
        # Không làm app chết; log ra stderr (journalctl sẽ thấy)
        app.logger.exception("Init DB failed: %s", e)

# ====== Health checks ======
@app.get("/health")
def health():
    # Cho ALB: luôn 200 nếu app sống
    return "ok", 200

@app.get("/dbhealth")
def dbhealth():
    # Kiểm DB: trả 200 nếu SELECT 1 thành công
    try:
        with get_conn(DB_NAME) as c:
            with c.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                _ = cur.fetchone()
        return "db ok", 200
    except Exception as e:
        app.logger.exception("DB health failed: %s", e)
        return ("db error", 500)

# ====== Ứng dụng ======
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        try:
            with get_conn(DB_NAME) as c:
                with c.cursor() as cur:
                    # Lấy ngẫu nhiên 5 câu hỏi
                    cur.execute(
                        "SELECT id, question, option_a, option_b, option_c, option_d "
                        "FROM questions ORDER BY RAND() LIMIT 5"
                    )
                    qs = cur.fetchall()
        except Exception as e:
            app.logger.exception("Load questions failed: %s", e)
            abort(500, description="Database connection failed")
        return render_template("index.html", questions=qs)

    # POST: chấm điểm
    username = request.form.get("username", "Guest").strip() or "Guest"
    answers = {k.split("_", 1)[1]: v for k, v in request.form.items() if k.startswith("q_")}
    if not answers:
        return redirect(url_for("index"))

    ids = list(answers.keys())
    try:
        with get_conn(DB_NAME) as c:
            with c.cursor() as cur:
                fmt = ",".join(["%s"] * len(ids))
                cur.execute(f"SELECT id, correct_option FROM questions WHERE id IN ({fmt})", ids)
                key = {str(row["id"]): row["correct_option"] for row in cur.fetchall()}
        score = sum(1 for i, opt in answers.items() if key.get(i) == opt)
        with get_conn(DB_NAME) as c:
            with c.cursor() as cur:
                cur.execute(
                    "INSERT INTO attempts(username, score, total) VALUES (%s,%s,%s)",
                    (username, score, len(ids)),
                )
    except Exception as e:
        app.logger.exception("Submit failed: %s", e)
        abort(500, description="Database write failed")

    return redirect(url_for("scores"))

@app.get("/scores")
def scores():
    try:
        with get_conn(DB_NAME) as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT username, score, total, created_at "
                    "FROM attempts ORDER BY id DESC LIMIT 10"
                )
                rows = cur.fetchall()
    except Exception as e:
        app.logger.exception("Load scores failed: %s", e)
        abort(500, description="Database connection failed")
    return render_template("scores.html", rows=rows)

# ====== Error handlers gọn gàng ======
@app.errorhandler(500)
def on_500(err):
    return (f"Lỗi hệ thống: {err.description if hasattr(err, 'description') else 'Internal error'}", 500)

@app.errorhandler(404)
def on_404(_):
    return ("Không tìm thấy trang", 404)
