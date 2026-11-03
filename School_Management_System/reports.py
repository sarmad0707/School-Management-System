
from flask import (
    Blueprint, render_template, redirect, url_for,
    session, flash, send_file
)
from database import get_connection

from io import BytesIO
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak
)
from xml.sax.saxutils import escape


reports_bp = Blueprint("reports", __name__)


def get_reports_data():
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        data = {}

        # Dashboard Summary
        cursor.execute("SELECT COUNT(*) AS total FROM students")
        data["total_students"] = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM teachers")
        data["total_teachers"] = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM classes")
        data["total_classes"] = cursor.fetchone()["total"]

        # Student Report
        cursor.execute("""
            SELECT
                s.student_id,
                s.admission_number,
                up.full_name AS student_name,
                c.class_name,
                sec.section_name,
                s.gender,
                s.date_of_birth
            FROM students s
            LEFT JOIN user_profiles up ON s.user_id = up.user_id
            LEFT JOIN classes c ON s.class_id = c.class_id
            LEFT JOIN sections sec ON s.section_id = sec.section_id
            ORDER BY s.student_id DESC
        """)
        data["student_report"] = cursor.fetchall()

        # Teacher Report
        cursor.execute("""
            SELECT
                t.teacher_id,
                up.full_name AS teacher_name,
                u.email,
                u.status,
                t.qualification,
                t.joining_date
            FROM teachers t
            LEFT JOIN user_profiles up ON t.user_id = up.user_id
            LEFT JOIN users u ON t.user_id = u.user_id
            ORDER BY t.teacher_id DESC
        """)
        data["teacher_report"] = cursor.fetchall()

        # Attendance Report
        cursor.execute("""
            SELECT
                at.type_name,
                COUNT(sa.attendance_id) AS total_records
            FROM attendance_types at
            LEFT JOIN student_attendance sa
                ON at.attendance_type_id = sa.attendance_type_id
            GROUP BY at.attendance_type_id, at.type_name
            ORDER BY at.type_name
        """)
        data["attendance_report"] = cursor.fetchall()

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM student_attendance
        """)
        data["total_attendance"] = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM student_attendance sa
            JOIN attendance_types at
                ON sa.attendance_type_id = at.attendance_type_id
            WHERE LOWER(at.type_name) = 'present'
        """)
        data["present_count"] = cursor.fetchone()["total"]

        total = data["total_attendance"]
        present = data["present_count"]

        data["attendance_percentage"] = (
            round((present / total) * 100, 2) if total > 0 else 0
        )

        # Fee Report
        cursor.execute("""
            SELECT
                sf.student_fee_id,
                s.admission_number,
                up.full_name AS student_name,
                c.class_name,
                ft.fee_name,
                fs.amount AS total_fee,
                COALESCE(paid.paid_amount, 0) AS paid_amount,
                fs.amount - COALESCE(paid.paid_amount, 0)
                    AS pending_amount,
                sf.due_date,
                sf.status
            FROM student_fees sf
            JOIN students s
                ON sf.student_id = s.student_id
            LEFT JOIN user_profiles up
                ON s.user_id = up.user_id
            LEFT JOIN classes c
                ON s.class_id = c.class_id
            JOIN fee_structures fs
                ON sf.fee_structure_id = fs.fee_structure_id
            LEFT JOIN fee_types ft
                ON fs.fee_type_id = ft.fee_type_id
            LEFT JOIN (
                SELECT
                    student_fee_id,
                    SUM(amount_paid) AS paid_amount
                FROM payments
                GROUP BY student_fee_id
            ) paid ON sf.student_fee_id = paid.student_fee_id
            ORDER BY sf.due_date DESC
        """)
        data["fee_report"] = cursor.fetchall()

        cursor.execute("""
            SELECT
                COALESCE(SUM(fs.amount), 0) AS total_fees,
                COALESCE(SUM(
                    COALESCE(paid.paid_amount, 0)
                ), 0) AS collected_fees,
                COALESCE(SUM(
                    fs.amount - COALESCE(paid.paid_amount, 0)
                ), 0) AS pending_fees
            FROM student_fees sf
            JOIN fee_structures fs
                ON sf.fee_structure_id = fs.fee_structure_id
            LEFT JOIN (
                SELECT
                    student_fee_id,
                    SUM(amount_paid) AS paid_amount
                FROM payments
                GROUP BY student_fee_id
            ) paid ON sf.student_fee_id = paid.student_fee_id
        """)
        data["fee_summary"] = cursor.fetchone()

        # Examination Results
        cursor.execute("""
            SELECT
                m.mark_id,
                up.full_name AS student_name,
                s.admission_number,
                c.class_name,
                e.exam_name,
                sub.subject_name,
                m.obtained_marks,
                es.total_marks,
                g.grade_name,
                e.exam_date
            FROM marks m
            JOIN students s
                ON m.student_id = s.student_id
            LEFT JOIN user_profiles up
                ON s.user_id = up.user_id
            LEFT JOIN classes c
                ON s.class_id = c.class_id
            JOIN exam_subjects es
                ON m.exam_subject_id = es.exam_subject_id
            JOIN exams e
                ON es.exam_id = e.exam_id
            JOIN subjects sub
                ON es.subject_id = sub.subject_id
            LEFT JOIN grades g
                ON m.grade_id = g.grade_id
            ORDER BY e.exam_date DESC, up.full_name
        """)
        data["exam_report"] = cursor.fetchall()

        return data

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def login_required():
    return "admin" in session


@reports_bp.route("/reports")
def reports():
    if not login_required():
        return redirect(url_for("login"))

    try:
        data = get_reports_data()
        return render_template("reports.html", **data)

    except Exception as e:
        print("Reports Error:", e)
        flash("Reports load nahi ho sakin. Terminal mein error check karein.", "danger")
        return redirect(url_for("dashboard"))


# EXCEL EXPORT
@reports_bp.route("/reports/export/excel")
def export_excel():
    if not login_required():
        return redirect(url_for("login"))

    try:
        data = get_reports_data()
        workbook = Workbook()

        # Summary Sheet
        sheet = workbook.active
        sheet.title = "Summary"

        summary_rows = [
            ["School Management System - Reports"],
            ["Report Generated", datetime.now().strftime("%Y-%m-%d %H:%M")],
            ["Total Students", data["total_students"]],
            ["Total Teachers", data["total_teachers"]],
            ["Total Classes", data["total_classes"]],
            ["Total Attendance Records", data["total_attendance"]],
            ["Present Records", data["present_count"]],
            ["Attendance Percentage", f'{data["attendance_percentage"]}%'],
            ["Total Fees", data["fee_summary"]["total_fees"]],
            ["Collected Fees", data["fee_summary"]["collected_fees"]],
            ["Pending Fees", data["fee_summary"]["pending_fees"]],
        ]

        for row in summary_rows:
            sheet.append(row)

        # Helper for creating Excel sheets
        def add_sheet(sheet_name, records, columns):
            ws = workbook.create_sheet(sheet_name)
            ws.append([heading for heading, key in columns])

            for record in records:
                ws.append([
                    record.get(key) for heading, key in columns
                ])

            return ws

        add_sheet("Students", data["student_report"], [
            ("Student ID", "student_id"),
            ("Admission No", "admission_number"),
            ("Student Name", "student_name"),
            ("Class", "class_name"),
            ("Section", "section_name"),
            ("Gender", "gender"),
            ("Date of Birth", "date_of_birth")
        ])

        add_sheet("Teachers", data["teacher_report"], [
            ("Teacher ID", "teacher_id"),
            ("Teacher Name", "teacher_name"),
            ("Email", "email"),
            ("Status", "status"),
            ("Qualification", "qualification"),
            ("Joining Date", "joining_date")
        ])

        add_sheet("Attendance", data["attendance_report"], [
            ("Attendance Type", "type_name"),
            ("Total Records", "total_records")
        ])

        add_sheet("Fees", data["fee_report"], [
            ("Fee ID", "student_fee_id"),
            ("Admission No", "admission_number"),
            ("Student Name", "student_name"),
            ("Class", "class_name"),
            ("Fee Type", "fee_name"),
            ("Total Fee", "total_fee"),
            ("Paid Amount", "paid_amount"),
            ("Pending Amount", "pending_amount"),
            ("Due Date", "due_date"),
            ("Status", "status")
        ])

        add_sheet("Exam Results", data["exam_report"], [
            ("Mark ID", "mark_id"),
            ("Student Name", "student_name"),
            ("Admission No", "admission_number"),
            ("Class", "class_name"),
            ("Exam", "exam_name"),
            ("Subject", "subject_name"),
            ("Obtained Marks", "obtained_marks"),
            ("Total Marks", "total_marks"),
            ("Grade", "grade_name"),
            ("Exam Date", "exam_date")
        ])

        # Style all sheets
        for ws in workbook.worksheets:
            ws.freeze_panes = "A2"

            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(
                    start_color="1F4E78",
                    end_color="1F4E78",
                    fill_type="solid"
                )
                cell.alignment = Alignment(horizontal="center")

            for column in ws.columns:
                max_length = 0
                column_letter = column[0].column_letter

                for cell in column:
                    value = cell.value
                    if value is not None:
                        max_length = max(max_length, len(str(value)))

                ws.column_dimensions[column_letter].width = min(
                    max_length + 4, 35
                )

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="school_management_reports.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        print("Excel Export Error:", e)
        flash("Excel file generate nahi hui. Terminal check karein.", "danger")
        return redirect(url_for("reports.reports"))


# PDF EXPORT
@reports_bp.route("/reports/export/pdf")
def export_pdf():
    if not login_required():
        return redirect(url_for("login"))

    try:
        data = get_reports_data()

        output = BytesIO()

        document = SimpleDocTemplate(
            output,
            pagesize=landscape(A4),
            rightMargin=10 * mm,
            leftMargin=10 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm
        )

        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(
            "School Management System",
            styles["Title"]
        ))
        story.append(Paragraph(
            "Complete Reports",
            styles["Heading2"]
        ))
        story.append(Paragraph(
            "Generated: " + datetime.now().strftime("%Y-%m-%d %H:%M"),
            styles["Normal"]
        ))
        story.append(Spacer(1, 12))

        # Summary
        story.append(Paragraph("Dashboard Summary", styles["Heading2"]))

        summary_data = [
            ["Report", "Value"],
            ["Total Students", str(data["total_students"])],
            ["Total Teachers", str(data["total_teachers"])],
            ["Total Classes", str(data["total_classes"])],
            ["Attendance Records", str(data["total_attendance"])],
            ["Present Records", str(data["present_count"])],
            ["Attendance Percentage", str(data["attendance_percentage"]) + "%"],
            ["Total Fees", str(data["fee_summary"]["total_fees"])],
            ["Collected Fees", str(data["fee_summary"]["collected_fees"])],
            ["Pending Fees", str(data["fee_summary"]["pending_fees"])]
        ]

        story.append(make_pdf_table(summary_data))
        story.append(Spacer(1, 15))

        def add_pdf_section(title, records, columns):
            story.append(Paragraph(title, styles["Heading2"]))

            table_data = [
                [heading for heading, key in columns]
            ]

            for record in records:
                table_data.append([
                    str(record.get(key) if record.get(key) is not None else "-")
                    for heading, key in columns
                ])

            if not records:
                table_data.append(["No records found"] + [""] * (len(columns) - 1))

            story.append(make_pdf_table(table_data))
            story.append(Spacer(1, 15))

        add_pdf_section("Student Report", data["student_report"], [
            ("ID", "student_id"),
            ("Admission No", "admission_number"),
            ("Name", "student_name"),
            ("Class", "class_name"),
            ("Section", "section_name"),
            ("Gender", "gender"),
            ("Date of Birth", "date_of_birth")
        ])

        add_pdf_section("Teacher Report", data["teacher_report"], [
            ("ID", "teacher_id"),
            ("Name", "teacher_name"),
            ("Email", "email"),
            ("Status", "status"),
            ("Qualification", "qualification"),
            ("Joining Date", "joining_date")
        ])

        add_pdf_section("Attendance Report", data["attendance_report"], [
            ("Attendance Type", "type_name"),
            ("Total Records", "total_records")
        ])

        add_pdf_section("Fee Report", data["fee_report"], [
            ("Fee ID", "student_fee_id"),
            ("Admission No", "admission_number"),
            ("Student", "student_name"),
            ("Class", "class_name"),
            ("Fee Type", "fee_name"),
            ("Total", "total_fee"),
            ("Paid", "paid_amount"),
            ("Pending", "pending_amount"),
            ("Due Date", "due_date"),
            ("Status", "status")
        ])

        add_pdf_section("Examination Results", data["exam_report"], [
            ("ID", "mark_id"),
            ("Student", "student_name"),
            ("Admission No", "admission_number"),
            ("Class", "class_name"),
            ("Exam", "exam_name"),
            ("Subject", "subject_name"),
            ("Obtained", "obtained_marks"),
            ("Total", "total_marks"),
            ("Grade", "grade_name"),
            ("Exam Date", "exam_date")
        ])

        document.build(story)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="school_management_reports.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:
        print("PDF Export Error:", e)
        flash("PDF file generate nahi hui. Terminal check karein.", "danger")
        return redirect(url_for("reports.reports"))


def make_pdf_table(table_data):
    safe_data = []

    for row in table_data:
        safe_row = []
        for value in row:
            safe_row.append(
                Paragraph(escape(str(value)), getSampleStyleSheet()["BodyText"])
            )
        safe_data.append(safe_row)

    table = Table(
        safe_data,
        repeatRows=1,
        hAlign="LEFT"
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#EAF0F6")
        ]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4)
    ]))

    return table


if __name__ == "__main__":
    print("Reports Blueprint is ready.")
