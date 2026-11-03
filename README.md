# School Management System

A web-based School Management System built with **Python, Flask, and MySQL**. It provides an admin dashboard for managing students, teachers, classes, attendance, fees, examinations, timetables, and reports.

## 1. Technologies Used

- Python
- Flask
- MySQL
- Jinja2 HTML templates
- ReportLab (PDF reports)
- OpenPyXL (Excel reports)
- python-dotenv (environment variables)

## 2. Main Features

- Admin login and dashboard
- Student management: add, edit, search, filter, and soft-delete
- Teacher management: add, edit, and soft-delete
- Classes and sections management
- Attendance entry and attendance reports
- Fee assignment and payment records
- Examination management and marks entry
- Student result cards
- Timetable management
- Reports with PDF and Excel export

## 3. Project Structure

```text
School_Management_System/
├── app.py
├── database.py
├── timetable.py
├── reports.py
├── .env
├── .gitignore
├── templates/
│   └── HTML template files
└── README.md
```

Your project may contain additional files or folders, such as `static/`. Keep them in their existing locations.

## 4. Requirements

- Windows 10/11
- Python
- MySQL Server
- VS Code (recommended)

## 5. Install Required Packages

Open the project folder in VS Code, then open its terminal and run:

```bash
python -m pip install Flask mysql-connector-python python-dotenv reportlab openpyxl
```

If a `requirements.txt` file is included in the project, you can install its packages with:

```bash
python -m pip install -r requirements.txt
```

## 6. Database Setup

1. Start MySQL Server.
2. Open MySQL Workbench or another MySQL client.
3. Make sure the database `school_management` exists.
4. Make sure the project's existing tables and records are available.
5. Configure the connection details in the `.env` file.

**Important:** Do not drop, recreate, or clear the database if it contains existing school data.

## 7. Environment Variables

Create a file named `.env` in the main project folder, alongside `app.py`.

Add your own local credentials:

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=school_management
SECRET_KEY=replace_with_a_long_random_secret
```

Replace the example values with your own MySQL password and a strong, private Flask secret key. Never share or upload your `.env` file.

Make sure `.gitignore` contains:

```gitignore
.env
__pycache__/
*.pyc
```

If a real database password or secret key has been exposed, change it.

## 8. Run the Application

In the VS Code terminal, go to the project folder and run:

```bash
python app.py
```

Open this address in your browser:

```text
http://127.0.0.1:5000
```

To stop the server, press `Ctrl + C` in the terminal.

## 9. Final Testing Checklist

Test each feature with suitable test records before demonstrating or submitting the project:

- [ ] Admin login and logout
- [ ] Dashboard
- [ ] Students: add, edit, search, filter, and soft-delete
- [ ] Teachers: add, edit, and soft-delete
- [ ] Classes and sections
- [ ] Attendance entry and attendance report
- [ ] Fee assignment and payment recording
- [ ] Exams and marks entry
- [ ] Student result card
- [ ] Timetable management
- [ ] Reports: PDF export
- [ ] Reports: Excel export

Tick an item only after confirming it works in your local environment.

## 10. Security Notes

- Keep database credentials and `SECRET_KEY` in `.env`.
- Do not upload `.env` to GitHub or share it with others.
- Use strong, unique passwords and a private Flask secret key.
- Keep Flask debug mode disabled outside development.
- Use HTTPS and secure session cookies when deploying publicly.
- Add CSRF protection to forms before public deployment.
- Change default or exposed login credentials before production use.
- Back up the database regularly.

## 11. Troubleshooting

### Database connection error

- Check that MySQL Server is running.
- Verify `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` in `.env`.
- Confirm that the MySQL user has permission to access `school_management`.

### Missing Python package

Install the missing package in the VS Code terminal:

```bash
python -m pip install package_name
```

### Port 5000 is already in use

Close the other application using port 5000, or configure Flask to use another available port.

---

**Project:** School Management System  
**Backend:** Python + Flask  
**Database:** MySQL  
**Run command:** `python app.py`
