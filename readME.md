# How to run the app
Commands for the terminal:

docker compose build

docker compose up -d db

docker compose run --rm web python manage.py makemigrations

docker compose run --rm web python manage.py migrate

docker compose up -d