import os
from datetime import date, timedelta

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)

from dotenv import load_dotenv
from database import get_connection
from werkzeug.security import check_password_hash, generate_password_hash

from timetable import timetable_bp
from reports import reports_bp


# =========================
# SECURITY CONFIGURATION
# =========================

load_dotenv()

app = Flask(__name__)

secret_key = os.getenv("SECRET_KEY")

if not secret_key:
    raise RuntimeError("SECRET_KEY .env file mein set nahi hai.")

app.config["SECRET_KEY"] = secret_key
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Local HTTP testing ke liye False.
# HTTPS hosting par isay True karna hoga.
app.config["SESSION_COOKIE_SECURE"] = False

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)


# =========================
# REGISTER BLUEPRINTS
# =========================

app.register_blueprint(timetable_bp)
app.register_blueprint(reports_bp)


# =========================
# HOME
# =========================

@app.route("/")
def home():
    if "admin" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# =========================
# ADMIN LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM admin WHERE username = %s",
                (username,)
            )

            admin = cursor.fetchone()

        finally:
            cursor.close()
            connection.close()

        if admin and check_password_hash(admin["password"], password):

            session.clear()
            session["admin"] = admin["username"]
            session.permanent = True

            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            error="Invalid username or password"
        )

    return render_template("login.html")


# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM students s
        JOIN users u ON s.user_id = u.user_id
        WHERE u.status = 'Active'
    """)

    total_students = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM teachers t
        JOIN users u ON t.user_id = u.user_id
        WHERE u.status = 'Active'
    """)

    total_teachers = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM classes
    """)

    total_classes = cursor.fetchone()["total"]

    cursor.close()
    connection.close()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        total_teachers=total_teachers,
        total_classes=total_classes
    )


# =========================
# CLASSES & SECTIONS MANAGEMENT
# =========================

@app.route("/classes", methods=["GET", "POST"])
def classes_management():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        try:
            action = request.form.get("action")

            # ADD CLASS
            if action == "add_class":

                class_name = request.form.get(
                    "class_name", ""
                ).strip()

                if not class_name:
                    raise Exception("Class name is required.")

                cursor.execute("""
                    SELECT class_id
                    FROM classes
                    WHERE LOWER(class_name) = LOWER(%s)
                """, (class_name,))

                if cursor.fetchone():
                    raise Exception("This class already exists.")

                cursor.execute("""
                    INSERT INTO classes (class_name, department_id)
                    VALUES (%s, NULL)
                """, (class_name,))

                connection.commit()
                flash("Class added successfully!")

            # ADD SECTION
            elif action == "add_section":

                class_id = request.form.get("class_id", type=int)

                section_name = request.form.get(
                    "section_name", ""
                ).strip()

                if not class_id or not section_name:
                    raise Exception(
                        "Please select a class and enter section name."
                    )

                cursor.execute("""
                    SELECT class_id
                    FROM classes
                    WHERE class_id = %s
                """, (class_id,))

                if not cursor.fetchone():
                    raise Exception("Selected class does not exist.")

                cursor.execute("""
                    SELECT section_id
                    FROM sections
                    WHERE class_id = %s
                    AND LOWER(section_name) = LOWER(%s)
                """, (class_id, section_name))

                if cursor.fetchone():
                    raise Exception(
                        "This section already exists in this class."
                    )

                cursor.execute("""
                    INSERT INTO sections (class_id, section_name)
                    VALUES (%s, %s)
                """, (class_id, section_name))

                connection.commit()
                flash("Section added successfully!")

            else:
                raise Exception("Invalid action.")

        except Exception as e:

            connection.rollback()
            flash("Error: " + str(e))

        finally:

            cursor.close()
            connection.close()

        return redirect(url_for("classes_management"))

    # GET CLASSES AND SECTIONS

    cursor.execute("""
        SELECT
            c.class_id,
            c.class_name,
            COUNT(DISTINCT sec.section_id) AS total_sections,
            COUNT(DISTINCT s.student_id) AS total_students
        FROM classes c
        LEFT JOIN sections sec
            ON c.class_id = sec.class_id
        LEFT JOIN students s
            ON c.class_id = s.class_id
        GROUP BY c.class_id, c.class_name
        ORDER BY c.class_id
    """)

    class_list = cursor.fetchall()

    cursor.execute("""
        SELECT
            sec.section_id,
            sec.section_name,
            sec.class_id,
            c.class_name,
            COUNT(s.student_id) AS total_students
        FROM sections sec
        JOIN classes c
            ON sec.class_id = c.class_id
        LEFT JOIN students s
            ON sec.section_id = s.section_id
        GROUP BY
            sec.section_id,
            sec.section_name,
            sec.class_id,
            c.class_name
        ORDER BY c.class_id, sec.section_name
    """)

    section_list = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "classes.html",
        classes=class_list,
        sections=section_list
    )


# =========================
# DELETE SECTION
# =========================

@app.route("/delete_section/<int:section_id>", methods=["POST"])
def delete_section(section_id):

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT section_id
            FROM sections
            WHERE section_id = %s
        """, (section_id,))

        section = cursor.fetchone()

        if not section:
            raise Exception("Section not found.")

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM students
            WHERE section_id = %s
        """, (section_id,))

        total_students = cursor.fetchone()["total"]

        if total_students > 0:
            raise Exception(
                "This section has students. Move those students "
                "to another section before deleting it."
            )

        cursor.execute("""
            DELETE FROM sections
            WHERE section_id = %s
        """, (section_id,))

        connection.commit()
        flash("Section deleted successfully!")

    except Exception as e:

        connection.rollback()
        flash("Delete Error: " + str(e))

    finally:

        cursor.close()
        connection.close()

    return redirect(url_for("classes_management"))


# =========================
# DELETE CLASS
# =========================

@app.route("/delete_class/<int:class_id>", methods=["POST"])
def delete_class(class_id):

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT class_id
            FROM classes
            WHERE class_id = %s
        """, (class_id,))

        if not cursor.fetchone():
            raise Exception("Class not found.")

        # Check students
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM students
            WHERE class_id = %s
        """, (class_id,))

        if cursor.fetchone()["total"] > 0:
            raise Exception(
                "This class has students. It cannot be deleted."
            )

        # Check sections
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM sections
            WHERE class_id = %s
        """, (class_id,))

        if cursor.fetchone()["total"] > 0:
            raise Exception(
                "Delete this class's sections before deleting the class."
            )

        # Check examination records
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM exam_subjects
            WHERE class_id = %s
        """, (class_id,))

        if cursor.fetchone()["total"] > 0:
            raise Exception(
                "This class has examination records and cannot be deleted."
            )

        # Check fee records
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM fee_structures
            WHERE class_id = %s
        """, (class_id,))

        if cursor.fetchone()["total"] > 0:
            raise Exception(
                "This class has fee records and cannot be deleted."
            )

        cursor.execute("""
            DELETE FROM classes
            WHERE class_id = %s
        """, (class_id,))

        connection.commit()
        flash("Class deleted successfully!")

    except Exception as e:

        connection.rollback()
        flash("Delete Error: " + str(e))

    finally:

        cursor.close()
        connection.close()

    return redirect(url_for("classes_management"))


# =========================
# STUDENT MANAGEMENT WITH SEARCH & FILTERS
# =========================

@app.route("/students")
def students():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    search_query = request.args.get("search", "").strip()
    selected_class = request.args.get("class_id", "").strip()
    selected_section = request.args.get("section_id", "").strip()

    query = """
        SELECT
            s.student_id,
            s.admission_number,
            s.date_of_birth,
            s.gender,
            up.full_name,
            up.phone,
            up.address,
            c.class_name,
            sec.section_name
        FROM students s
        JOIN users u ON s.user_id = u.user_id
        LEFT JOIN user_profiles up ON s.user_id = up.user_id
        LEFT JOIN classes c ON s.class_id = c.class_id
        LEFT JOIN sections sec ON s.section_id = sec.section_id
        WHERE u.status = 'Active'
    """

    params = []

    # Search by name or admission number
    if search_query:

        query += """
            AND (
                up.full_name LIKE %s
                OR s.admission_number LIKE %s
            )
        """

        search_value = "%" + search_query + "%"
        params.extend([search_value, search_value])

    # Class filter
    if selected_class:

        query += " AND s.class_id = %s"
        params.append(selected_class)

    # Section filter
    if selected_section:

        query += " AND s.section_id = %s"
        params.append(selected_section)

    query += " ORDER BY s.student_id DESC"

    try:

        cursor.execute(query, tuple(params))
        student_list = cursor.fetchall()

        # Get classes
        cursor.execute("""
            SELECT class_id, class_name
            FROM classes
            ORDER BY class_id
        """)

        class_list = cursor.fetchall()

        # Get sections
        cursor.execute("""
            SELECT section_id, section_name, class_id
            FROM sections
            ORDER BY class_id, section_name
        """)

        section_list = cursor.fetchall()

    finally:

        cursor.close()
        connection.close()

    return render_template(
        "students.html",
        students=student_list,
        classes=class_list,
        sections=section_list,
        search_query=search_query,
        selected_class=selected_class,
        selected_section=selected_section
    )


# =========================
# ADD STUDENT
# =========================

@app.route("/add_student", methods=["GET", "POST"])
def add_student():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        try:

            full_name = request.form["full_name"]
            username = request.form["username"]
            email = request.form.get("email") or None

            password = generate_password_hash(
                request.form["password"]
            )

            phone = request.form.get("phone")
            address = request.form.get("address")

            admission_number = (
                request.form.get("admission_number") or None
            )

            dob = request.form.get("date_of_birth") or None
            gender = request.form.get("gender")
            class_id = request.form.get("class_id") or None
            section_id = request.form.get("section_id") or None

            cursor.execute("""
                INSERT INTO users (username, email, password, status)
                VALUES (%s, %s, %s, 'Active')
            """, (username, email, password))

            user_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO user_profiles
                (user_id, full_name, phone, address)
                VALUES (%s, %s, %s, %s)
            """, (user_id, full_name, phone, address))

            cursor.execute("""
                SELECT role_id
                FROM roles
                WHERE role_name = 'Student'
            """)

            role = cursor.fetchone()

            if not role:
                raise Exception(
                    "Student role database mein nahi mila."
                )

            cursor.execute("""
                INSERT INTO user_roles (user_id, role_id)
                VALUES (%s, %s)
            """, (user_id, role["role_id"]))

            cursor.execute("""
                INSERT INTO students
                (
                    user_id, class_id, section_id,
                    admission_number, date_of_birth, gender
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                class_id,
                section_id,
                admission_number,
                dob,
                gender
            ))

            connection.commit()

            flash("Student added successfully!")
            return redirect(url_for("students"))

        except Exception as e:

            connection.rollback()
            return f"Student Error: {e}"

        finally:

            cursor.close()
            connection.close()

    cursor.execute("""
        SELECT *
        FROM classes
        ORDER BY class_id
    """)

    classes = cursor.fetchall()

    cursor.execute("""
        SELECT *
        FROM sections
        ORDER BY section_id
    """)

    sections = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "add_student.html",
        classes=classes,
        sections=sections
    )


# =========================
# EDIT STUDENT
# =========================

@app.route("/edit_student/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        try:

            cursor.execute("""
                SELECT user_id
                FROM students
                WHERE student_id = %s
            """, (student_id,))

            student = cursor.fetchone()

            if not student:
                return "Student not found", 404

            user_id = student["user_id"]

            cursor.execute("""
                UPDATE user_profiles
                SET full_name = %s, phone = %s, address = %s
                WHERE user_id = %s
            """, (
                request.form["full_name"],
                request.form.get("phone"),
                request.form.get("address"),
                user_id
            ))

            cursor.execute("""
                UPDATE students
                SET
                    admission_number = %s,
                    date_of_birth = %s,
                    gender = %s,
                    class_id = %s,
                    section_id = %s
                WHERE student_id = %s
            """, (
                request.form.get("admission_number") or None,
                request.form.get("date_of_birth") or None,
                request.form.get("gender"),
                request.form.get("class_id") or None,
                request.form.get("section_id") or None,
                student_id
            ))

            connection.commit()

            return redirect(url_for("students"))

        except Exception as e:

            connection.rollback()
            return f"Student Update Error: {e}"

        finally:

            cursor.close()
            connection.close()

    cursor.execute("""
        SELECT
            s.*,
            up.full_name,
            up.phone,
            up.address
        FROM students s
        LEFT JOIN user_profiles up ON s.user_id = up.user_id
        WHERE s.student_id = %s
    """, (student_id,))

    student = cursor.fetchone()

    cursor.execute("""
        SELECT *
        FROM classes
        ORDER BY class_id
    """)

    classes = cursor.fetchall()

    cursor.execute("""
        SELECT *
        FROM sections
        ORDER BY section_id
    """)

    sections = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "edit_student.html",
        student=student,
        classes=classes,
        sections=sections
    )


# =========================
# DELETE STUDENT
# =========================

@app.route("/delete_student/<int:student_id>", methods=["POST"])
def delete_student(student_id):

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE users
        SET status = 'Inactive'
        WHERE user_id = (
            SELECT user_id
            FROM students
            WHERE student_id = %s
        )
    """, (student_id,))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("students"))


# =========================
# TEACHER MANAGEMENT
# =========================

@app.route("/teachers")
def teachers():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            t.teacher_id,
            t.qualification,
            t.joining_date,
            up.full_name,
            up.phone,
            up.address
        FROM teachers t
        JOIN users u ON t.user_id = u.user_id
        LEFT JOIN user_profiles up ON t.user_id = up.user_id
        WHERE u.status = 'Active'
        ORDER BY t.teacher_id DESC
    """)

    teacher_list = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "teachers.html",
        teachers=teacher_list
    )


# =========================
# ADD TEACHER
# =========================

@app.route("/add_teacher", methods=["GET", "POST"])
def add_teacher():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        try:

            full_name = request.form["full_name"]
            username = request.form["username"]
            email = request.form.get("email") or None

            password = generate_password_hash(
                request.form["password"]
            )

            phone = request.form.get("phone")
            address = request.form.get("address")
            qualification = request.form.get("qualification")
            joining_date = request.form.get("joining_date") or None

            cursor.execute("""
                INSERT INTO users (username, email, password, status)
                VALUES (%s, %s, %s, 'Active')
            """, (username, email, password))

            user_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO user_profiles
                (user_id, full_name, phone, address)
                VALUES (%s, %s, %s, %s)
            """, (user_id, full_name, phone, address))

            cursor.execute("""
                SELECT role_id
                FROM roles
                WHERE role_name = 'Teacher'
            """)

            role = cursor.fetchone()

            if not role:
                raise Exception(
                    "Teacher role database mein nahi mila."
                )

            cursor.execute("""
                INSERT INTO user_roles (user_id, role_id)
                VALUES (%s, %s)
            """, (user_id, role["role_id"]))

            cursor.execute("""
                INSERT INTO teachers
                (user_id, qualification, joining_date)
                VALUES (%s, %s, %s)
            """, (user_id, qualification, joining_date))

            connection.commit()

            return redirect(url_for("teachers"))

        except Exception as e:

            connection.rollback()
            return f"Teacher Error: {e}"

        finally:

            cursor.close()
            connection.close()

    cursor.close()
    connection.close()

    return render_template("add_teacher.html")


# =========================
# EDIT TEACHER
# =========================

@app.route("/edit_teacher/<int:teacher_id>", methods=["GET", "POST"])
def edit_teacher(teacher_id):

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        try:

            cursor.execute("""
                SELECT user_id
                FROM teachers
                WHERE teacher_id = %s
            """, (teacher_id,))

            teacher = cursor.fetchone()

            if not teacher:
                return "Teacher not found", 404

            user_id = teacher["user_id"]

            cursor.execute("""
                UPDATE user_profiles
                SET full_name = %s, phone = %s, address = %s
                WHERE user_id = %s
            """, (
                request.form["full_name"],
                request.form.get("phone"),
                request.form.get("address"),
                user_id
            ))

            cursor.execute("""
                UPDATE teachers
                SET qualification = %s, joining_date = %s
                WHERE teacher_id = %s
            """, (
                request.form.get("qualification"),
                request.form.get("joining_date") or None,
                teacher_id
            ))

            connection.commit()

            return redirect(url_for("teachers"))

        except Exception as e:

            connection.rollback()
            return f"Teacher Update Error: {e}"

        finally:

            cursor.close()
            connection.close()

    cursor.execute("""
        SELECT
            t.*,
            up.full_name,
            up.phone,
            up.address
        FROM teachers t
        LEFT JOIN user_profiles up ON t.user_id = up.user_id
        WHERE t.teacher_id = %s
    """, (teacher_id,))

    teacher = cursor.fetchone()

    cursor.close()
    connection.close()

    return render_template(
        "edit_teacher.html",
        teacher=teacher
    )


# =========================
# DELETE TEACHER
# =========================

@app.route("/delete_teacher/<int:teacher_id>", methods=["POST"])
def delete_teacher(teacher_id):

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE users
        SET status = 'Inactive'
        WHERE user_id = (
            SELECT user_id
            FROM teachers
            WHERE teacher_id = %s
        )
    """, (teacher_id,))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect(url_for("teachers"))


# =========================
# ATTENDANCE MANAGEMENT
# =========================

@app.route("/attendance", methods=["GET", "POST"])
def attendance():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        try:

            class_id = request.form["class_id"]
            section_id = request.form["section_id"]
            attendance_date = request.form["attendance_date"]

            cursor.execute("""
                SELECT s.student_id
                FROM students s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.class_id = %s
                AND s.section_id = %s
                AND u.status = 'Active'
            """, (class_id, section_id))

            students_list = cursor.fetchall()

            for student in students_list:

                student_id = student["student_id"]

                status = request.form.get(
                    f"status_{student_id}"
                )

                if not status:
                    continue

                cursor.execute("""
                    SELECT attendance_type_id
                    FROM attendance_types
                    WHERE type_name = %s
                """, (status,))

                attendance_type = cursor.fetchone()

                if not attendance_type:
                    raise Exception(
                        "Attendance type not found: " + status
                    )

                type_id = attendance_type["attendance_type_id"]

                cursor.execute("""
                    SELECT attendance_id
                    FROM student_attendance
                    WHERE student_id = %s
                    AND attendance_date = %s
                """, (student_id, attendance_date))

                existing = cursor.fetchone()

                if existing:

                    cursor.execute("""
                        UPDATE student_attendance
                        SET attendance_type_id = %s
                        WHERE attendance_id = %s
                    """, (
                        type_id,
                        existing["attendance_id"]
                    ))

                else:

                    cursor.execute("""
                        INSERT INTO student_attendance
                        (
                            student_id,
                            attendance_type_id,
                            attendance_date
                        )
                        VALUES (%s, %s, %s)
                    """, (
                        student_id,
                        type_id,
                        attendance_date
                    ))

            connection.commit()

            return redirect(url_for("attendance_report"))

        except Exception as e:

            connection.rollback()
            return f"Attendance Error: {e}"

        finally:

            cursor.close()
            connection.close()

    class_id = request.args.get("class_id")
    section_id = request.args.get("section_id")

    attendance_date = (
        request.args.get("attendance_date")
        or date.today().isoformat()
    )

    cursor.execute("""
        SELECT *
        FROM classes
        ORDER BY class_id
    """)

    classes = cursor.fetchall()

    cursor.execute("""
        SELECT section_id, section_name, class_id
        FROM sections
        ORDER BY class_id, section_name
    """)

    sections = cursor.fetchall()

    students = []

    if class_id and section_id:

        cursor.execute("""
            SELECT section_id
            FROM sections
            WHERE section_id = %s
            AND class_id = %s
        """, (section_id, class_id))

        if cursor.fetchone():

            cursor.execute("""
                SELECT
                    s.student_id,
                    s.admission_number,
                    up.full_name,
                    c.class_name,
                    sec.section_name
                FROM students s
                JOIN users u ON s.user_id = u.user_id
                LEFT JOIN user_profiles up ON s.user_id = up.user_id
                LEFT JOIN classes c ON s.class_id = c.class_id
                LEFT JOIN sections sec ON s.section_id = sec.section_id
                WHERE s.class_id = %s
                AND s.section_id = %s
                AND u.status = 'Active'
                ORDER BY up.full_name
            """, (class_id, section_id))

            students = cursor.fetchall()

            for student in students:

                cursor.execute("""
                    SELECT at.type_name
                    FROM student_attendance sa
                    JOIN attendance_types at
                    ON sa.attendance_type_id = at.attendance_type_id
                    WHERE sa.student_id = %s
                    AND sa.attendance_date = %s
                    ORDER BY sa.attendance_id DESC
                    LIMIT 1
                """, (
                    student["student_id"],
                    attendance_date
                ))

                old_record = cursor.fetchone()

                student["old_status"] = (
                    old_record["type_name"]
                    if old_record else "Present"
                )

    cursor.execute("""
        SELECT type_name
        FROM attendance_types
        ORDER BY attendance_type_id
    """)

    attendance_types = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "attendance.html",
        classes=classes,
        sections=sections,
        students=students,
        attendance_types=attendance_types,
        selected_class=class_id,
        selected_section=section_id,
        attendance_date=attendance_date
    )


# =========================
# ATTENDANCE REPORT
# =========================

@app.route("/attendance_report")
def attendance_report():

    if "admin" not in session:
        return redirect(url_for("login"))

    attendance_date = request.args.get("date")

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    query = """
        SELECT
            s.student_id,
            up.full_name,
            s.admission_number,
            c.class_name,
            sec.section_name,
            at.type_name,
            sa.attendance_date
        FROM student_attendance sa
        JOIN students s ON sa.student_id = s.student_id
        JOIN attendance_types at
            ON sa.attendance_type_id = at.attendance_type_id
        LEFT JOIN user_profiles up ON s.user_id = up.user_id
        LEFT JOIN classes c ON s.class_id = c.class_id
        LEFT JOIN sections sec ON s.section_id = sec.section_id
    """

    if attendance_date:

        query += """
            WHERE sa.attendance_date = %s
            ORDER BY up.full_name
        """

        cursor.execute(query, (attendance_date,))

    else:

        query += """
            ORDER BY sa.attendance_date DESC, up.full_name
        """

        cursor.execute(query)

    records = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "attendance_report.html",
        records=records,
        attendance_date=attendance_date
    )


# =========================
# FEE MANAGEMENT
# =========================

@app.route("/fees")
def fees():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            s.student_id,
            s.admission_number,
            up.full_name
        FROM students s
        JOIN users u ON s.user_id = u.user_id
        LEFT JOIN user_profiles up ON s.user_id = up.user_id
        WHERE u.status = 'Active'
        ORDER BY up.full_name
    """)

    students = cursor.fetchall()

    cursor.execute("""
        SELECT
            MIN(fs.fee_structure_id) AS fee_structure_id,
            ft.fee_name,
            c.class_name,
            fs.class_id,
            fs.amount,
            ay.year_name
        FROM fee_structures fs
        JOIN fee_types ft ON fs.fee_type_id = ft.fee_type_id
        JOIN classes c ON fs.class_id = c.class_id
        JOIN academic_years ay
            ON fs.academic_year_id = ay.academic_year_id
        GROUP BY
            ft.fee_name,
            c.class_name,
            fs.class_id,
            fs.amount,
            ay.year_name
        ORDER BY fs.class_id
    """)

    fee_structures = cursor.fetchall()

    cursor.execute("""
        SELECT
            sf.student_fee_id,
            s.student_id,
            up.full_name,
            s.admission_number,
            c.class_name,
            ft.fee_name,
            fs.amount AS total_fee,
            COALESCE(SUM(p.amount_paid), 0) AS paid_amount,
            fs.amount - COALESCE(SUM(p.amount_paid), 0) AS balance,
            sf.due_date,
            CASE
                WHEN COALESCE(SUM(p.amount_paid), 0) >= fs.amount
                    THEN 'Paid'
                WHEN COALESCE(SUM(p.amount_paid), 0) > 0
                    THEN 'Partial'
                ELSE 'Pending'
            END AS status
        FROM student_fees sf
        JOIN students s ON sf.student_id = s.student_id
        JOIN user_profiles up ON s.user_id = up.user_id
        JOIN fee_structures fs
            ON sf.fee_structure_id = fs.fee_structure_id
        JOIN fee_types ft ON fs.fee_type_id = ft.fee_type_id
        LEFT JOIN classes c ON s.class_id = c.class_id
        LEFT JOIN payments p
            ON sf.student_fee_id = p.student_fee_id
        GROUP BY
            sf.student_fee_id,
            s.student_id,
            up.full_name,
            s.admission_number,
            c.class_name,
            ft.fee_name,
            fs.amount,
            sf.due_date
        ORDER BY sf.student_fee_id DESC
    """)

    fee_records = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "fees.html",
        students=students,
        fee_structures=fee_structures,
        fee_records=fee_records
    )


# =========================
# ASSIGN STUDENT FEE
# =========================

@app.route("/assign_fee", methods=["POST"])
def assign_fee():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        student_id = request.form["student_id"]
        fee_structure_id = request.form["fee_structure_id"]
        due_date = request.form["due_date"]

        cursor.execute("""
            SELECT s.student_id
            FROM students s
            JOIN users u ON s.user_id = u.user_id
            JOIN fee_structures fs ON s.class_id = fs.class_id
            WHERE s.student_id = %s
            AND fs.fee_structure_id = %s
            AND u.status = 'Active'
        """, (student_id, fee_structure_id))

        if not cursor.fetchone():
            raise Exception(
                "Selected fee does not match student's class."
            )

        cursor.execute("""
            SELECT student_fee_id
            FROM student_fees
            WHERE student_id = %s
            AND fee_structure_id = %s
            AND due_date = %s
        """, (
            student_id,
            fee_structure_id,
            due_date
        ))

        if cursor.fetchone():
            raise Exception(
                "This fee is already assigned to this student."
            )

        cursor.execute("""
            INSERT INTO student_fees
            (student_id, fee_structure_id, due_date, status)
            VALUES (%s, %s, %s, 'Pending')
        """, (
            student_id,
            fee_structure_id,
            due_date
        ))

        connection.commit()
        flash("Student fee assigned successfully!")

    except Exception as e:

        connection.rollback()
        flash("Fee Assignment Error: " + str(e))

    finally:

        cursor.close()
        connection.close()

    return redirect(url_for("fees"))


# =========================
# RECEIVE FEE PAYMENT
# =========================

@app.route("/record_payment", methods=["POST"])
def record_payment():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        student_fee_id = request.form["student_fee_id"]
        amount_paid = float(request.form["amount_paid"])
        payment_date = request.form["payment_date"]
        payment_method = request.form["payment_method"]

        if amount_paid <= 0:
            raise Exception(
                "Payment amount must be greater than zero."
            )

        cursor.execute("""
            SELECT fs.amount
            FROM student_fees sf
            JOIN fee_structures fs
                ON sf.fee_structure_id = fs.fee_structure_id
            WHERE sf.student_fee_id = %s
        """, (student_fee_id,))

        fee = cursor.fetchone()

        if not fee:
            raise Exception("Student fee record not found.")

        total_fee = float(fee["amount"])

        cursor.execute("""
            SELECT COALESCE(SUM(amount_paid), 0) AS paid
            FROM payments
            WHERE student_fee_id = %s
        """, (student_fee_id,))

        already_paid = float(cursor.fetchone()["paid"])

        remaining = total_fee - already_paid

        if remaining <= 0:
            raise Exception("This fee is already fully paid.")

        if amount_paid > remaining:
            raise Exception(
                f"Payment exceeds remaining balance. "
                f"Remaining: Rs. {remaining:.2f}"
            )

        cursor.execute("""
            INSERT INTO payments
            (
                student_fee_id,
                amount_paid,
                payment_date,
                payment_method
            )
            VALUES (%s, %s, %s, %s)
        """, (
            student_fee_id,
            amount_paid,
            payment_date,
            payment_method
        ))

        new_paid = already_paid + amount_paid

        if new_paid >= total_fee:
            status = "Paid"

        elif new_paid > 0:
            status = "Partial"

        else:
            status = "Pending"

        cursor.execute("""
            UPDATE student_fees
            SET status = %s
            WHERE student_fee_id = %s
        """, (status, student_fee_id))

        connection.commit()
        flash("Payment received successfully!")

    except Exception as e:

        connection.rollback()
        flash("Payment Error: " + str(e))

    finally:

        cursor.close()
        connection.close()

    return redirect(url_for("fees"))


# =========================
# EXAMINATION MANAGEMENT
# =========================

@app.route("/exams")
def exams():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            e.exam_id,
            e.exam_name,
            e.exam_date,
            ay.year_name
        FROM exams e
        LEFT JOIN academic_years ay
            ON e.academic_year_id = ay.academic_year_id
        ORDER BY e.exam_date DESC
    """)

    exam_list = cursor.fetchall()

    cursor.execute("""
        SELECT class_id, class_name
        FROM classes
        ORDER BY class_id
    """)

    classes = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "exams.html",
        exams=exam_list,
        classes=classes
    )


# =========================
# MARKS ENTRY
# =========================

@app.route("/marks_entry", methods=["GET", "POST"])
def marks_entry():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        try:

            exam_id = int(request.form["exam_id"])
            class_id = int(request.form["class_id"])
            exam_subject_id = int(
                request.form["exam_subject_id"]
            )

            cursor.execute("""
                SELECT total_marks
                FROM exam_subjects
                WHERE exam_subject_id = %s
                AND exam_id = %s
                AND class_id = %s
            """, (
                exam_subject_id,
                exam_id,
                class_id
            ))

            exam_subject = cursor.fetchone()

            if not exam_subject:
                raise Exception(
                    "Selected exam subject is invalid."
                )

            total_marks = float(exam_subject["total_marks"])

            cursor.execute("""
                SELECT s.student_id
                FROM students s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.class_id = %s
                AND u.status = 'Active'
            """, (class_id,))

            class_students = cursor.fetchall()

            for student in class_students:

                student_id = student["student_id"]

                value = request.form.get(
                    f"marks_{student_id}"
                )

                if value is None or value.strip() == "":
                    continue

                obtained_marks = float(value)

                if obtained_marks < 0 or obtained_marks > total_marks:
                    raise Exception(
                        f"Student ID {student_id}: marks 0 se "
                        f"{total_marks} ke darmiyan hone chahiye."
                    )

                percentage = (
                    obtained_marks / total_marks
                ) * 100

                cursor.execute("""
                    SELECT grade_id
                    FROM grades
                    WHERE %s >= minimum_percentage
                    AND %s <= maximum_percentage
                    ORDER BY minimum_percentage DESC
                    LIMIT 1
                """, (
                    percentage,
                    percentage
                ))

                grade = cursor.fetchone()

                grade_id = (
                    grade["grade_id"] if grade else None
                )

                cursor.execute("""
                    SELECT mark_id
                    FROM marks
                    WHERE student_id = %s
                    AND exam_subject_id = %s
                """, (
                    student_id,
                    exam_subject_id
                ))

                existing = cursor.fetchone()

                if existing:

                    cursor.execute("""
                        UPDATE marks
                        SET obtained_marks = %s, grade_id = %s
                        WHERE mark_id = %s
                    """, (
                        obtained_marks,
                        grade_id,
                        existing["mark_id"]
                    ))

                else:

                    cursor.execute("""
                        INSERT INTO marks
                        (
                            student_id,
                            exam_subject_id,
                            obtained_marks,
                            grade_id
                        )
                        VALUES (%s, %s, %s, %s)
                    """, (
                        student_id,
                        exam_subject_id,
                        obtained_marks,
                        grade_id
                    ))

            connection.commit()

            flash("Marks saved successfully!")

            return redirect(url_for(
                "marks_entry",
                exam_id=exam_id,
                class_id=class_id,
                exam_subject_id=exam_subject_id
            ))

        except Exception as e:

            connection.rollback()
            flash("Marks Entry Error: " + str(e))

        finally:

            cursor.close()
            connection.close()

        return redirect(url_for("marks_entry"))

    exam_id = request.args.get("exam_id", type=int)
    class_id = request.args.get("class_id", type=int)

    exam_subject_id = request.args.get(
        "exam_subject_id",
        type=int
    )

    cursor.execute("""
        SELECT exam_id, exam_name
        FROM exams
        ORDER BY exam_date DESC
    """)

    exam_list = cursor.fetchall()

    cursor.execute("""
        SELECT class_id, class_name
        FROM classes
        ORDER BY class_id
    """)

    classes = cursor.fetchall()

    subjects = []
    students = []

    if exam_id and class_id:

        cursor.execute("""
            SELECT
                es.exam_subject_id,
                es.total_marks,
                s.subject_name
            FROM exam_subjects es
            JOIN subjects s ON es.subject_id = s.subject_id
            WHERE es.exam_id = %s
            AND es.class_id = %s
            ORDER BY s.subject_name
        """, (exam_id, class_id))

        subjects = cursor.fetchall()

    if exam_id and class_id and exam_subject_id:

        cursor.execute("""
            SELECT total_marks
            FROM exam_subjects
            WHERE exam_subject_id = %s
            AND exam_id = %s
            AND class_id = %s
        """, (
            exam_subject_id,
            exam_id,
            class_id
        ))

        selected_subject = cursor.fetchone()

        if selected_subject:

            cursor.execute("""
                SELECT
                    s.student_id,
                    s.admission_number,
                    up.full_name,
                    m.obtained_marks
                FROM students s
                JOIN users u ON s.user_id = u.user_id
                LEFT JOIN user_profiles up ON s.user_id = up.user_id
                LEFT JOIN marks m
                    ON m.student_id = s.student_id
                    AND m.exam_subject_id = %s
                WHERE s.class_id = %s
                AND u.status = 'Active'
                ORDER BY up.full_name
            """, (
                exam_subject_id,
                class_id
            ))

            students = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "marks_entry.html",
        exams=exam_list,
        classes=classes,
        subjects=subjects,
        students=students,
        selected_exam=exam_id,
        selected_class=class_id,
        selected_subject=exam_subject_id
    )


# =========================
# STUDENT RESULT CARD
# =========================

@app.route("/result_card/<int:student_id>")
def result_card(student_id):

    if "admin" not in session:
        return redirect(url_for("login"))

    exam_id = request.args.get("exam_id", type=int)

    if not exam_id:
        flash("Please select an exam.")
        return redirect(url_for("exams"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            s.student_id,
            s.admission_number,
            up.full_name,
            c.class_name
        FROM students s
        JOIN users u ON s.user_id = u.user_id
        LEFT JOIN user_profiles up ON s.user_id = up.user_id
        LEFT JOIN classes c ON s.class_id = c.class_id
        WHERE s.student_id = %s
    """, (student_id,))

    student = cursor.fetchone()

    if not student:

        cursor.close()
        connection.close()

        return "Student not found", 404

    cursor.execute("""
        SELECT exam_name
        FROM exams
        WHERE exam_id = %s
    """, (exam_id,))

    exam = cursor.fetchone()

    if not exam:

        cursor.close()
        connection.close()

        return "Exam not found", 404

    cursor.execute("""
        SELECT
            sub.subject_name,
            es.total_marks,
            m.obtained_marks,
            g.grade_name
        FROM exam_subjects es
        JOIN subjects sub ON es.subject_id = sub.subject_id
        LEFT JOIN marks m
            ON m.exam_subject_id = es.exam_subject_id
            AND m.student_id = %s
        LEFT JOIN grades g ON m.grade_id = g.grade_id
        WHERE es.exam_id = %s
        AND es.class_id = (
            SELECT class_id
            FROM students
            WHERE student_id = %s
        )
        ORDER BY sub.subject_name
    """, (
        student_id,
        exam_id,
        student_id
    ))

    result_rows = cursor.fetchall()

    total_marks = sum(
        float(row["total_marks"] or 0)
        for row in result_rows
    )

    obtained_total = sum(
        float(row["obtained_marks"] or 0)
        for row in result_rows
    )

    percentage = (
        (obtained_total / total_marks) * 100
        if total_marks > 0 else 0
    )

    cursor.execute("""
        SELECT grade_name
        FROM grades
        WHERE %s >= minimum_percentage
        AND %s <= maximum_percentage
        ORDER BY minimum_percentage DESC
        LIMIT 1
    """, (
        percentage,
        percentage
    ))

    overall_grade = cursor.fetchone()

    overall_grade = (
        overall_grade["grade_name"]
        if overall_grade else "N/A"
    )

    entered_subjects = sum(
        1 for row in result_rows
        if row["obtained_marks"] is not None
    )

    result_status = (
        "Complete"
        if entered_subjects == len(result_rows)
        else "Incomplete"
    )

    cursor.close()
    connection.close()

    return render_template(
        "result_card.html",
        student=student,
        exam=exam,
        results=result_rows,
        total_marks=total_marks,
        obtained_total=obtained_total,
        percentage=round(percentage, 2),
        overall_grade=overall_grade,
        result_status=result_status
    )


# =========================
# ADMIN LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =========================
# RUN APPLICATION
# =========================

if __name__ == "__main__":

    app.run(debug=False)