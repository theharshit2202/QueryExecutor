"""
WTForms for form validation.
"""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, PasswordField
from wtforms.validators import DataRequired, Length, ValidationError


class LoginForm(FlaskForm):
    """Login form."""
    username = StringField(
        'Username',
        validators=[DataRequired(message='Username is required.'), Length(min=3, max=50)],
        render_kw={'placeholder': 'Enter your username', 'class': 'form-control'}
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired(message='Password is required.'), Length(min=3)],
        render_kw={'placeholder': 'Enter your password', 'class': 'form-control'}
    )
    remember_me = BooleanField('Remember Me', default=False)


class QueryForm(FlaskForm):
    """SQL Query form."""
    sql_query = TextAreaField(
        'SQL Query',
        validators=[DataRequired(message='SQL query is required.')],
        render_kw={
            'placeholder': 'Enter your SQL query (SELECT statements only)',
            'class': 'form-control',
            'rows': 8
        }
    )
    defect_number = StringField(
        'Defect Number',
        validators=[DataRequired(message='Defect number is required.'), Length(max=100)],
        render_kw={'placeholder': 'Enter defect number', 'class': 'form-control'}
    )
    database = SelectField(
        'Database',
        choices=[('BackOffice', 'BackOffice'), ('Portal', 'Portal')],
        validators=[DataRequired(message='Please select a database.')],
        render_kw={'class': 'form-select'}
    )
    
    def validate_sql_query(self, field):
        """Custom validation for SQL query."""
        import re
        query = field.data.strip()
        if not query:
            raise ValidationError('SQL query cannot be empty.')
        
        # Remove comments and normalize whitespace
        query_clean = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
        query_clean = re.sub(r'/\*.*?\*/', '', query_clean, flags=re.DOTALL)
        query_clean = ' '.join(query_clean.split())
        query_upper = query_clean.upper()
        
        # Check for SELECT statement (case-insensitive)
        if not query_upper.startswith('SELECT'):
            raise ValidationError('Only SELECT queries are allowed.')

