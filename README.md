# EDMS - Enterprise Document Management System

A web-based document management system built with Flask, Python and SQLite.
It lets a team upload, organise, version, search and approve documents, with
role-based access and a full audit trail.

**Live demo:** https://raj2006.pythonanywhere.com

## Features

- **Login and security**: Flask-Login sessions, CSRF protection on every form and API call, account lockout (5 wrong passwords blocks that username for about 10 minutes), POST-only logout, secure session cookies and security headers.
- **Roles**: Admin and User. In strict access mode, normal users see only their own documents; admins see everything.
- **Sign-up page**: people can create their own account. The role is always User, passwords need 12 or more characters, duplicate usernames and emails are blocked, and each sign-up is recorded in the audit trail.
- **Documents**: upload (25 MB limit), preview, download, metadata (department, reference number, description, status), delete (admin only).
- **Versions**: upload new versions and download any older version.
- **Folders**: folders and subfolders, move documents between folders.
- **Search and filters**: text search, folder / status / department / file type filters, upload date range, and saved searches (stored in the browser per user).
- **Retention and legal hold**: retention date and legal hold both block deletion.
- **Approval workflow**: Draft -> Pending (Submit for Approval) -> Active (Approve) or back to Draft (Reject, with optional reason). Only admins can approve or reject.
- **Audit trail**: logins, failed logins, document actions, folder actions and approval actions, with user, time and IP address.
- **Dashboard**: totals, charts by status, department and file type, retention deadlines, latest activity.
- **Responsive UI**: works on desktop and phone (slide-in menu, card layout for documents).

## Tech stack

Python, Flask 3.1.3, Flask-Login, Flask-SQLAlchemy, Flask-Migrate, Flask-WTF, SQLite, plain HTML, CSS and JavaScript (no frontend framework, no chart libraries).

## Setup (Windows, PowerShell)

1. Open PowerShell in the project folder (`C:\EDMS-Project`).
2. Create and activate a virtual environment (first time only):

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. Install the packages:

   ```powershell
   pip install -r requirements.txt
   ```

4. Set the secret key (required, set it in every new PowerShell window):

   ```powershell
   $env:EDMS_SECRET_KEY = "put-a-long-random-text-here"
   ```

5. Start the app:

   ```powershell
   python run.py
   ```

6. Open `http://127.0.0.1:5000` in your browser and log in.

Passwords must be at least 12 characters long.

## Project structure

```
EDMS-Project/
  run.py                  App setup, CSRF, security headers, dashboard stats API
  requirements.txt        Python packages
  app/
    models/
      document.py         Folder, Document, DocumentVersion, AuditLog
      user.py             User model (hashed passwords)
    routes/
      auth_routes.py      Login, logout, lockout
      document_routes.py  Documents, versions, audit and user-role APIs
      folder_routes.py    Folder pages and API
      approval_routes.py  Submit / approve / reject
      user_routes.py      User management pages
    extensions.py         Flask extensions
  templates/
    index.html            Dashboard and Documents page
    folders.html          Folder Management
    activity.html         Audit activity page
    user_management.html  User Management
    login.html            Login page
  storage/
    edms.db               SQLite database
    uploads/              Uploaded files
```

## Approval workflow

| Action | Who | Status change | Audit action |
|---|---|---|---|
| Submit for Approval | Uploader or admin | Draft -> Pending | APPROVAL_SUBMIT |
| Approve | Admin only | Pending -> Active | APPROVAL_APPROVE |
| Reject | Admin only | Pending -> Draft | APPROVAL_REJECT |

## Before a demo or submission

- Make sure `debug=False` in `run.py`.
- Do not share `storage/edms.db` or the `uploads` folders if they contain real documents.
- Keep passwords out of screenshots and chats.

## Testing

A test checklist is in `EDMS_Test_Checklist.xlsx` (test cases, expected results, status and screenshot tracking).
