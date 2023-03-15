# Projeto de Gestão de Bens Patrimoniais

## Descrição

O projeto foi desenvolvido para o setor de Bens Patrimoniais da Secretaria Municipal de São Paulo. Possui dois tipos de usuários: Gestor de Patrimônio e Operador de Inventário.

### Funcionalidades

- Cadastro de Bem Patrimonial
- Aprovação de Cadastro de Bem Patrimonial
- Movimentação de Bem Patrimonial
- Configuração de Agenda do Setor de Bem Patrimonial
- Agendamento de Reunião de Suporte
- Cadastro de Unidade Administrativa
- Cadastro de Usuário
- Login

### Modelos

- BemPatrimonial
- UnidadeAdministrativaBemPatrimonial
- MovimentacaoBemPatrimonial
- StatusBemPatrimonial
- UnidadeAdministrativa
- Usuario
- ConfigAgendaSuporte
- DiaSemana
- IntervaloHoras
- AgendamentoSuporte

### Permissões

- O Gestor de Patrimônio tem acesso a todas as funcionalidades.
- O Operador de Inventário só tem acesso a cadastrar patrimônio, agendar reunião de suporte e solicitar movimentação de um bem patrimonial.

## Movimentação de bens patrimoniais

- Para realizar a movimentação de um bem patrimonial entre unidades administrativas, é necessário criar uma instância do modelo MovimentacaoBemPatrimonial com os dados da movimentação, incluindo o bem patrimonial, as unidades administrativas de origem e destino e a quantidade a ser movimentada.
- É necessário que haja a aprovação por parte do operador da unidade destino. Após aprovação, a quantidade é debitada ou creditada.

## Tecnologias

- Django 4.1.3
- Django Admin
- Python 3.11
- PostgreSQL

## Instalação

1. Faça o clone do repositório.

2. Crie um ambiente virtual:

   ```
   python -m venv venv
   ```

3. Ative o ambiente virtual:

   ```
   source venv/bin/activate
   ```

4. Instale as dependências:

   ```
   pip install -r requirements.txt
   ```

5. Crie um banco de dados PostgreSQL e configure as variáveis de ambiente para a conexão com o banco de dados.

6. Execute as migrações:

   ```
   python manage.py migrate
   ```

7. Crie um superusuário:

   ```
   python manage.py createsuperuser
   ```

8. Execute scripts de configuração para funcionamento correto:

   ```
   python manage.py setup_grupos_e_permissoes
   python manage.py setup_agenda
   ```

9. Execute o servidor:

   ```
   python manage.py runserver
   ```
