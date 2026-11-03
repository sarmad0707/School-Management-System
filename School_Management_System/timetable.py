
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_connection

timetable_bp = Blueprint("timetable", __name__)


@timetable_bp.route("/timetable", methods=["GET", "POST"])
def timetable():

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == "POST":

        try:
            class_id = request.form["class_id"]
            section_id = request.form["section_id"]
            academic_year_id = request.form["academic_year_id"]
            subject_id = request.form["subject_id"]
            teacher_id = request.form["teacher_id"]
            day_name = request.form["day_name"]
            start_time = request.form["start_time"]
            end_time = request.form["end_time"]

            if start_time >= end_time:
                flash("End time must be later than start time!", "error")
                return redirect(url_for("timetable.timetable"))

            cursor.execute(
                """
                SELECT section_id FROM sections
                WHERE section_id=%s AND class_id=%s
                """,
                (section_id, class_id)
            )

            if not cursor.fetchone():
                flash("Invalid section selected!", "error")
                return redirect(url_for("timetable.timetable"))

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM timetable_periods tp
                JOIN timetables t ON tp.timetable_id=t.timetable_id
                WHERE t.class_id=%s
                AND t.section_id=%s
                AND t.academic_year_id=%s
                AND tp.day_name=%s
                AND tp.start_time < %s
                AND tp.end_time > %s
                """,
                (
                    class_id, section_id, academic_year_id,
                    day_name, end_time, start_time
                )
            )

            if cursor.fetchone()["total"] > 0:
                flash("This class already has a period at this time!", "error")
                return redirect(url_for("timetable.timetable"))

            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM timetable_periods
                WHERE teacher_id=%s
                AND day_name=%s
                AND start_time < %s
                AND end_time > %s
                """,
                (teacher_id, day_name, end_time, start_time)
            )

            if cursor.fetchone()["total"] > 0:
                flash("This teacher already has a class at this time!", "error")
                return redirect(url_for("timetable.timetable"))

            cursor.execute(
                """
                SELECT timetable_id FROM timetables
                WHERE class_id=%s
                AND section_id=%s
                AND academic_year_id=%s
                """,
                (class_id, section_id, academic_year_id)
            )

            timetable_record = cursor.fetchone()

            if timetable_record:
                timetable_id = timetable_record["timetable_id"]
            else:
                cursor.execute(
                    """
                    INSERT INTO timetables
                    (class_id, section_id, academic_year_id)
                    VALUES (%s, %s, %s)
                    """,
                    (class_id, section_id, academic_year_id)
                )
                timetable_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO timetable_periods
                (timetable_id, subject_id, teacher_id, classroom_id,
                 day_name, start_time, end_time)
                VALUES (%s, %s, %s, NULL, %s, %s, %s)
                """,
                (
                    timetable_id, subject_id, teacher_id,
                    day_name, start_time, end_time
                )
            )

            connection.commit()
            flash("Timetable period added successfully!", "success")

        except Exception as e:
            connection.rollback()
            flash(f"Error: {str(e)}", "error")

        finally:
            cursor.close()
            connection.close()

        return redirect(url_for("timetable.timetable"))

    cursor.execute(
        "SELECT class_id, class_name FROM classes ORDER BY class_name"
    )
    classes = cursor.fetchall()

    cursor.execute(
        """
        SELECT section_id, section_name, class_id
        FROM sections
        ORDER BY class_id, section_name
        """
    )
    sections = cursor.fetchall()

    cursor.execute(
        """
        SELECT academic_year_id, year_name
        FROM academic_years
        ORDER BY academic_year_id DESC
        """
    )
    academic_years = cursor.fetchall()

    cursor.execute(
        "SELECT subject_id, subject_name FROM subjects ORDER BY subject_name"
    )
    subjects = cursor.fetchall()

    cursor.execute(
        """
        SELECT t.teacher_id, up.full_name
        FROM teachers t
        LEFT JOIN user_profiles up ON t.user_id=up.user_id
        JOIN users u ON t.user_id=u.user_id
        WHERE u.status='Active'
        ORDER BY up.full_name
        """
    )
    teachers = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            tp.period_id,
            tp.day_name,
            tp.start_time,
            tp.end_time,
            c.class_name,
            sec.section_name,
            ay.year_name,
            sub.subject_name,
            up.full_name AS teacher_name
        FROM timetable_periods tp
        JOIN timetables t ON tp.timetable_id=t.timetable_id
        JOIN classes c ON t.class_id=c.class_id
        JOIN sections sec ON t.section_id=sec.section_id
        JOIN academic_years ay ON t.academic_year_id=ay.academic_year_id
        JOIN subjects sub ON tp.subject_id=sub.subject_id
        JOIN teachers te ON tp.teacher_id=te.teacher_id
        LEFT JOIN user_profiles up ON te.user_id=up.user_id
        ORDER BY
            FIELD(tp.day_name,
            'Monday','Tuesday','Wednesday','Thursday',
            'Friday','Saturday','Sunday'),
            tp.start_time
        """
    )
    periods = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "timetable.html",
        classes=classes,
        sections=sections,
        academic_years=academic_years,
        subjects=subjects,
        teachers=teachers,
        periods=periods
    )


@timetable_bp.route("/delete_timetable_period/<int:period_id>", methods=["POST"])
def delete_timetable_period(period_id):

    if "admin" not in session:
        return redirect(url_for("login"))

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM timetable_periods WHERE period_id=%s",
            (period_id,)
        )

        if cursor.rowcount > 0:
            connection.commit()
            flash("Timetable period deleted successfully!", "success")
        else:
            flash("Timetable period not found!", "error")

    except Exception as e:
        connection.rollback()
        flash(f"Error: {str(e)}", "error")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("timetable.timetable"))
