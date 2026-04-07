-- MySQL 8+: create database (name without hyphen avoids URL quoting issues)
CREATE DATABASE IF NOT EXISTS pizzashop_api
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- If you prefer the name with a hyphen, create it as:
-- CREATE DATABASE IF NOT EXISTS `pizzashop-api` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- Then set DATABASE_URL to: mysql+pymysql://root:root@127.0.0.1:3306/pizzashop%2Dapi
