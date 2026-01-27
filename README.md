# HR Anonymous Message Module for Odoo 19

## Overview
This Odoo module allows employees to send anonymous messages to HR, enabling confidential reporting of issues or feedback. HR staff can view, acknowledge, and resolve messages. The module also includes configurable email notifications.

## Features
- Employees can submit anonymous messages.
- HR managers can view, acknowledge, and resolve messages.
- Automatic email notifications to HR when a message is submitted.
- HR internal notes for private tracking.
- Configurable HR email address via Settings → General Settings → HR Anonymous Messages**.
- Permissions system: restrict certain fields to HR/Admin users.

## Installation

## 1. Clone the repository into your Odoo `addons` directory:

```bash
git clone https://github.com/busayo524/# HR Anonymous Message Module for Odoo 19

## Environment Setup

Follow these steps to prepare your environment to run Odoo 19 and the HR Anonymous Message module.

### 1. Install Python
- Odoo 19 works best with **Python 3.11**.
- Download and install Python from: [https://www.python.org/downloads/](https://www.python.org/downloads/)
- Make sure to **check "Add Python to PATH"** during installation.

Verify installation:
```bash
python --version
pip --version

### 2. Install PostgreSQL
- Download PostgreSQL: https://www.postgresql.org/download/windows/
- Install it and remember the username/password (default user is usually postgres).
- Create a database for Odoo (optional, can be done from Odoo web interface).

### 3. Set up a Virtual Environment
- cd C:\Odoo_2
- python -m venv venv
- .\venv\Scripts\activate
- deactivate - to deactivate python environment

### 4. Install required packages (should be done in the virtual environment)
- pip install --upgrade pip wheel
- pip install -r requirements.txt

### 5. Configure odoo
- Make sure your odoo.conf file is correctly set with database and addons paths.
- Example minimal odoo.conf:
[options]
addons_path = C:\Odoo_2\addons,C:\Odoo_2\custom_addons
db_host = localhost
db_port = 5432
db_user = yourusername
db_password = yourpassword
logfile = C:\Odoo_2\odoo.log

### 6. run odoo
- cd C:\Odoo_2
- .\venv\Scripts\activate
- python odoo\odoo-bin -c odoo.conf
- Open your browser: http://localhost:8069
- Create a new database or use an existing one.

### 7. Install the HR Anonymous Message Module
- Go to setting -> Activate developer settings
- Go to Apps → Update Apps List
- Search for HR Anonymous Message
- Click Install
- Configure HR email in Settings → General Settings → HR Anonymous Messages



