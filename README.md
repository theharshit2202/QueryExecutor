<<<<<<< HEAD
# Shubham Kotkar 2.0 - Secure SQL Query Executor

A modern, secure Flask web application that allows authenticated users to safely execute SQL queries on approved databases.

## 🎯 Features

- **Secure Authentication**: Flask-Login based authentication with password hashing
- **SQL Query Execution**: Safe execution of SELECT queries with DML protection
- **Database Support**: Support for multiple databases (BackOffice and Portal)
- **Security Features**:
  - SQL injection protection via parameterized queries
  - DML statement blocking (UPDATE, DELETE, DROP, TRUNCATE, etc.)
  - CSRF protection via Flask-WTF
  - Security headers (X-Frame-Options, CSP, etc.)
  - Session management with timeout
- **Modern UI**: Bootstrap 5 with blue/white theme
- **Responsive Design**: Mobile-friendly interface
- **Result Pagination**: Efficient handling of large result sets
- **Error Handling**: Graceful error pages for 403, 404, 500

## 📋 Prerequisites

- Python 3.8 or higher
- MySQL/MariaDB database server
- pip (Python package manager)

## 🚀 Installation

1. **Clone or navigate to the project directory:**
   ```bash
   cd "D:\Shubham Kotkar 2.0"
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv venv
   
   # On Windows:
   venv\Scripts\activate
   
   # On Linux/Mac:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   
   Create a `.env` file in the project root with the following content:
   ```env
   # Flask Configuration
   SECRET_KEY=your-secret-key-here-change-in-production
   FLASK_ENV=development
   FLASK_DEBUG=1

   # Database Configuration - BackOffice
   BACKOFFICE_DB_HOST=localhost
   BACKOFFICE_DB_PORT=3306
   BACKOFFICE_DB_USER=your_db_user
   BACKOFFICE_DB_PASSWORD=your_db_password
   BACKOFFICE_DB_NAME=your_backoffice_db

   # Database Configuration - Portal
   PORTAL_DB_HOST=localhost
   PORTAL_DB_PORT=3306
   PORTAL_DB_USER=your_db_user
   PORTAL_DB_PASSWORD=your_db_password
   PORTAL_DB_NAME=your_portal_db

   # Session Configuration
   SESSION_TIMEOUT_MINUTES=30
   ```
   
   **Important**: 
   - Replace all placeholder values with your actual database credentials
   - Generate a strong `SECRET_KEY` for production (use `python -c "import secrets; print(secrets.token_hex(32))"`)

5. **Default Login Credentials:**
   - Username: `admin`
   - Password: `password`
   
   **⚠️ IMPORTANT**: Change these credentials in production! Edit the `users` dictionary in `app.py` or implement a proper user database.

## 🏃 Running the Application

1. **Activate your virtual environment** (if not already activated)

2. **Run the Flask application:**
   ```bash
   python app.py
   ```

3. **Access the application:**
   - Open your browser and navigate to: `http://localhost:5000`
   - You'll be redirected to the login page
   - Use the default credentials to log in

## 📁 Project Structure

```
Shubham Kotkar 2.0/
├── app.py                 # Main Flask application
├── forms.py              # WTForms for form validation
├── requirements.txt      # Python dependencies
├── README.md            # This file
├── .env                 # Environment variables (create this)
├── utils/
│   └── db.py           # Database connection utilities
├── templates/
│   ├── base.html       # Base template
│   ├── login.html      # Login page
│   ├── query.html      # Query executor page
│   ├── result.html     # Results display page
│   └── error.html      # Error pages (403, 404, 500)
└── static/
    └── css/
        └── style.css   # Custom styles
```

## 🔒 Security Features

### SQL Injection Protection
- All queries are validated for DML statements
- Parameterized queries are used (when applicable)
- Only SELECT statements are allowed

### Authentication & Authorization
- Password hashing using Werkzeug's security utilities
- Session-based authentication with Flask-Login
- Protected routes using `@login_required` decorator
- Session timeout for inactivity

### CSRF Protection
- Flask-WTF CSRF tokens on all forms
- Automatic token validation

### Security Headers
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- X-XSS-Protection: 1; mode=block
- Content-Security-Policy

## 🎨 UI/UX Features

- **Modern Design**: Bootstrap 5 with custom blue (#0056D2) theme
- **Responsive Layout**: Works on desktop, tablet, and mobile
- **Loading Indicators**: Elegant spinner during query execution
- **Form Validation**: Client-side and server-side validation
- **Error Messages**: User-friendly error displays
- **Result Pagination**: Efficient handling of large datasets

## 📝 Usage

1. **Login**: Access the application and log in with your credentials
2. **Execute Query**: 
   - Enter your SQL query (SELECT only)
   - Provide a defect number
   - Select the target database (BackOffice or Portal)
   - Click "Execute Query"
3. **View Results**: Results are displayed in a formatted table with pagination
4. **Logout**: Click the logout button in the navigation bar

## ⚠️ Important Notes

1. **Production Deployment**:
   - Change the default `SECRET_KEY` in `.env`
   - Change default admin credentials
   - Set `FLASK_DEBUG=0` in production
   - Use a production WSGI server (e.g., Gunicorn, uWSGI)
   - Configure proper database credentials
   - Set up HTTPS/SSL

2. **Database Configuration**:
   - Ensure MySQL/MariaDB server is running
   - Create databases or use existing ones
   - Grant appropriate read-only permissions to the database user
   - Test connections before running the application

3. **Query Restrictions**:
   - Only SELECT queries are allowed
   - DML operations (UPDATE, DELETE, DROP, TRUNCATE, etc.) are blocked
   - Complex queries may take time depending on database size

## 🐛 Troubleshooting

### Database Connection Errors
- Verify database credentials in `.env`
- Ensure MySQL server is running
- Check network connectivity
- Verify database user has proper permissions

### Import Errors
- Ensure virtual environment is activated
- Run `pip install -r requirements.txt` again
- Check Python version (3.8+ required)

### Login Issues
- Verify you're using correct credentials (default: admin/password)
- Check browser console for errors
- Clear browser cookies/cache

## 🔧 Development

To modify the application:

1. **Add New Users**: Edit the `users` dictionary in `app.py`
2. **Customize Styles**: Modify `static/css/style.css`
3. **Add Routes**: Create new blueprints or add routes to `app.py`
4. **Database Changes**: Update `utils/db.py` for connection logic

## 📄 License

This project is for internal use. All rights reserved.

## 👤 Author

Shubham Kotkar 2.0

---

**Note**: This application is designed for secure internal use. Always follow your organization's security policies when deploying to production.

=======
# QueryExecutor
>>>>>>> 77512e5d9d42dc3ab3fa79eba205eaef5849a3a9
