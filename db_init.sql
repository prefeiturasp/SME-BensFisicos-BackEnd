-- Cria ROLE e DB somente se não existirem
DO
$$
BEGIN
   IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'app_user') THEN
      EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L;', :'app_user', :'app_pass');
   END IF;

   IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db') THEN
      EXECUTE format('CREATE DATABASE %I OWNER %I;', :'app_db', :'app_user');
   END IF;
END
$$;

-- Garantir privilégios (idempotente)
GRANT ALL PRIVILEGES ON DATABASE :app_db TO :app_user;