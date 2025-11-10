"""
WTForms for authentication and admin user management.
"""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SelectField
from wtforms.validators import DataRequired, Length, EqualTo


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


class CreateUserForm(FlaskForm):
    """Admin: Create new user."""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Role', choices=[('user', 'User'), ('admin', 'Admin')], validators=[DataRequired()])


class ResetPasswordForm(FlaskForm):
    """Admin: Reset user password."""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('new_password')])


class BulkUploadForm(FlaskForm):
    """Admin: Bulk upload users from CSV file."""
    csv_file = FileField(
        'CSV File',
        validators=[
            FileRequired(message='Please select a CSV file.'),
            FileAllowed(['csv'], message='Only CSV files are allowed.')
        ],
        render_kw={'accept': '.csv', 'class': 'form-control'}
    )

