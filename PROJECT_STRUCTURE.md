# Project Structure

```
Shubham Kotkar 2.0/
├── app.py                    # Main Flask application with routes and configuration
├── forms.py                  # WTForms for form validation (LoginForm, QueryForm)
├── requirements.txt          # Python dependencies
├── README.md                 # Setup and usage instructions
├── env_template.txt          # Environment variables template (copy to .env)
├── PROJECT_STRUCTURE.md      # This file
│
├── utils/
│   └── db.py                # Database connection and query execution utilities
│
├── templates/
│   ├── base.html            # Base template with navigation and Bootstrap layout
│   ├── login.html           # Login page template
│   ├── query.html           # Query executor form template
│   ├── result.html          # Query results display template
│   └── error.html           # Error pages template (403, 404, 500)
│
└── static/
    └── css/
        └── style.css        # Custom styles with blue (#0056D2) theme
```

## Key Files

### app.py
- Flask application initialization
- Authentication setup with Flask-Login
- CSRF protection with Flask-WTF
- Security headers configuration
- Routes: `/`, `/login`, `/logout`, `/query`, `/result`
- Error handlers: 403, 404, 500
- Session management with timeout

### forms.py
- `LoginForm`: Username, password, remember me
- `QueryForm`: SQL query, defect number, database selection
- Custom validation for SQL queries (SELECT only)

### utils/db.py
- `DatabaseManager` class
- Connection management for BackOffice and Portal databases
- DML statement detection and blocking
- Safe query execution with error handling

### Templates
- **base.html**: Shared layout with navigation bar
- **login.html**: Authentication form
- **query.html**: SQL query input form with loading spinner
- **result.html**: Results table with pagination
- **error.html**: Error pages with helpful messages

## Security Features

1. **SQL Injection Protection**: Parameterized queries and DML blocking
2. **CSRF Protection**: Flask-WTF tokens on all forms
3. **Authentication**: Flask-Login with password hashing
4. **Session Management**: Timeout after inactivity
5. **Security Headers**: X-Frame-Options, CSP, X-XSS-Protection
6. **Input Validation**: Server-side and client-side validation

## Default Credentials

- Username: `admin`
- Password: `password`

**⚠️ Change these in production!**

## Next Steps

1. Copy `env_template.txt` to `.env` and configure database credentials
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `python app.py`
4. Access at: `http://localhost:5000`

