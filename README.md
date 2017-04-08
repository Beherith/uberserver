# Requirements
- python 3
- sqlalchemy
- GeoIP
- twisted

# Installation
```
# git clone git@github.com:spring/uberserver.git
# virtualenv ~/virtenvs/uberserver
# source ~/virtenvs/uberserver/bin/activate
# pip install SQLAlchemy pycrypto twisted pyOpenSSL GeoIP mysqlclient
```

Without further configuration this will create a SQLite database (server.db).
Performance will be OK for testing and small setups. For production use,
setup MySQL/PostgreSQL/etc.

# Usage
```
# source ~/virtenvs/uberserver/bin/activate
# ./server.py
```

# Logs
- `$PWD/server.log`
