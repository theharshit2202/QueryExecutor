-- Database initialization script for Shubham Kotkar 2.0
-- Run this script on your database to create required tables

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert default admin user (password: 'password')
-- Note: Password hash is generated using werkzeug.security.generate_password_hash
-- You should change this password after first login
INSERT IGNORE INTO users (username, password_hash) VALUES 
('admin', 'pbkdf2:sha256:600000$YourSecretSalt$YourHashedPassword');

-- Audit Log Table
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INT AUTO_INCREMENT PRIMARY KEY,
    audit_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    executed_by_user VARCHAR(100),
    query_text TEXT,
    database_name VARCHAR(50),
    status ENUM('Pending','Success','Error','Rejected by user') DEFAULT 'Pending',
    defect_number VARCHAR(50),
    rows_affected INT DEFAULT 0,
    error_message TEXT,
    INDEX idx_user (executed_by_user),
    INDEX idx_timestamp (audit_timestamp),
    INDEX idx_status (status),
    INDEX idx_database (database_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Note: Replace 'YourSecretSalt' and 'YourHashedPassword' with actual values
-- Generate password hash using Python:
-- from werkzeug.security import generate_password_hash
-- print(generate_password_hash('password'))

