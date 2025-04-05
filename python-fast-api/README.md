# Fast API Otel Instrumentation

## Usage

1. Clone the repository
```shell
git clone https://github.com/base-14/examples.git
cd examples/python-fast-api
```

2. Start the postgres server as a docker container

```shell
docker compose up -d
```

3. Populate the `.env` file

```dotenv
DB_HOSTNAME=localhost
DB_PORT=5432
DB_PASSWORD=SecurePassHere
DB_NAME=fastapi
DB_USERNAME=postgres
SECRET_KEY=549e20314db0f2fbc78705c6b6d9ab5367d34ece54d90c4cf6c655e9dda0
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

4. Start the python server

```shell
python -m uvicorn app.main:app
```

Go to http://127.0.0.1:8000/docs once running for built-in documentation.
