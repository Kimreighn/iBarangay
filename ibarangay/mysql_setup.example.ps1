$env:MYSQL_HOST = '127.0.0.1'
$env:MYSQL_PORT = '3306'
$env:MYSQL_USER = 'root'
$env:MYSQL_PASSWORD = 'your_mysql_password'
$env:MYSQL_DATABASE = 'ibarangay'

# Optional alternative:
# $env:DATABASE_URL = 'mysql+pymysql://root:your_mysql_password@127.0.0.1:3306/ibarangay'

python migrate_to_mysql.py
python app.py
