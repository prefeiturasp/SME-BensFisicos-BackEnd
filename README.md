# API e Admin para site Projetos Rápidos

> COTIC-DISIS tem uma equipe exclusiva para realização de pequenas demandas da Secretaria Municipal de Educação de São Paulo. Esta frente de desenvolvimento é focada em demandas mais simples, mas que apoiarão uma parte de seu trabalho no dia a dia ou que ajudarão você e sua equipe em iniciativas pontuais.

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

Via Django Admin

- CRUD solicitações, mensagens de contato e seções.
- Filtros solicitações
- Exportação de relatórios

Via API

- Criação de solicitação, criação de mensagem e busca de seções da landing page.

## Rodar os testes

Com o env ativado, rode o seguinte comando:

$ python manage.py test

Para rodar por app, rode o seguinte o comando:

$ python manage.py test <app>
