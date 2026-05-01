import os
import unittest
from unittest.mock import patch

from database_config import build_mysql_uri, get_database_uri, get_sqlite_uri


class DatabaseConfigTestCase(unittest.TestCase):
    def test_defaults_to_sqlite_when_mysql_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_database_uri(), get_sqlite_uri())

    def test_builds_mysql_uri_from_env(self):
        with patch.dict(os.environ, {
            'MYSQL_HOST': '127.0.0.1',
            'MYSQL_USER': 'root',
            'MYSQL_PASSWORD': 'secret123',
            'MYSQL_PORT': '3307',
            'MYSQL_DATABASE': 'ibarangay_test',
        }, clear=True):
            self.assertEqual(
                build_mysql_uri(),
                'mysql+pymysql://root:secret123@127.0.0.1:3307/ibarangay_test?charset=utf8mb4'
            )

    def test_prefers_database_url_when_present(self):
        with patch.dict(os.environ, {
            'DATABASE_URL': 'mysql://demo:pass@localhost/sampledb'
        }, clear=True):
            self.assertEqual(
                get_database_uri(),
                'mysql+pymysql://demo:pass@localhost/sampledb'
            )


if __name__ == '__main__':
    unittest.main()
