CREATE TABLE IF NOT EXISTS clientes (
    id             SERIAL PRIMARY KEY,
    nombre         VARCHAR(100) NOT NULL,
    email          VARCHAR(150) NOT NULL,
    fecha_registro DATE
);

-- Rol de solo lectura que usa la página web vía PostgREST
CREATE ROLE web_anon NOLOGIN;
GRANT USAGE ON SCHEMA public TO web_anon;
GRANT SELECT ON clientes TO web_anon;
GRANT web_anon TO nifi;

-- Botón "Vaciar tabla" de la página: borra todo y reinicia los id a 1
CREATE OR REPLACE FUNCTION reiniciar_clientes() RETURNS void
LANGUAGE sql SECURITY DEFINER AS $$
    TRUNCATE clientes RESTART IDENTITY;
$$;
GRANT EXECUTE ON FUNCTION reiniciar_clientes() TO web_anon;
