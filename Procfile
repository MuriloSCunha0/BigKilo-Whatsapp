web: python manage.py migrate --noinput && python manage.py compilemessages -l pt_BR && python manage.py collectstatic --noinput && uvicorn config.asgi:application --host 0.0.0.0 --port $PORT
