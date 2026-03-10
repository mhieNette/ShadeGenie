CREATE DATABASE shadegenie;
USE shadegenie;

CREATE TABLE skin_genie_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    admin_flag ENUM('Y', 'N') NOT NULL
);

DESC skin_genie_users;

SELECT * FROM shadegenie.skin_genie_users;

INSERT INTO shadegenie.skin_genie_users (EMAIL, password, admin_flag)
VALUES ('testuser01@test.com', 'testuser01', 'N');

INSERT INTO shadegenie.skin_genie_users (EMAIL, password, admin_flag)
VALUES ('admin@test.com', 'admin123', 'Y');