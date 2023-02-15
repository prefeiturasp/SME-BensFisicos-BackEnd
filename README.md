# Sistema de cadastro de bens físicos para o setor de Bens Patrimoniais da SME.

## Prerequisitos

- Python 3.11

## Instalação

Passo a passo para instalar e rodar o projeto local

$ python3 -m venv /path/to/new/virtual/environment

- Ative o ambiente

$ pip install -r requirements.txt

$ cp env.sample

$ python manage.py migrate

$ python manage.py createsuperuser

$ python manage.py runserver 0.0.0.0:8000

Pronto. Agora você pode acessar seu localhost/admin e logar com as credenciais criadas.

## Funcionalidades

- CRUD de bens patrimoniais
- CRUD de usuários
- CRUD de unidades administrativas

## Rodar os testes

Com o env ativado, rode o seguinte comando:

$ python manage.py test

Para rodar por app, rode o seguinte o comando:

$ python manage.py test <app>
