init-db:
	docker compose -f docker-compose-dev.yml run --rm web python manage.py migrate
	docker compose -f docker-compose-dev.yml run --rm web python manage.py shell -c "from django.contrib.auth import get_user_model; import os; User=get_user_model(); u=os.getenv('SUPER_USER','smebensfisicos'); p=os.getenv('SUPER_USER_PASSWORD','smebens'); e=os.getenv('SUPER_USER_EMAIL','admin@example.com'); User.objects.filter(username=u).exists() or User.objects.create_superuser(username=u,email=e,password=p)"
seed-base:
	docker compose -f docker-compose-dev.yml run --rm web python manage.py seed_bensfisicos_demo
setup-grupos-permissoes:
	docker compose -f docker-compose-dev.yml run --rm web python manage.py setup_grupos_e_permissoes