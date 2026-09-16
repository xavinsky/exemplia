-- Rôle en lecture seule utilisé par l'exemple d'analyse de données.
CREATE ROLE lecteur LOGIN PASSWORD 'lecteur';
GRANT CONNECT ON DATABASE entreprise TO lecteur;
GRANT USAGE ON SCHEMA public TO lecteur;
-- Les tables sont créées plus tard par le rôle iacu : les droits sont donnés par défaut.
ALTER DEFAULT PRIVILEGES FOR ROLE iacu IN SCHEMA public GRANT SELECT ON TABLES TO lecteur;
ALTER ROLE lecteur SET statement_timeout = '5s';
ALTER ROLE lecteur SET default_transaction_read_only = on;
