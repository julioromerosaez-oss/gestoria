-- =====================================================================
-- Gestoría · esquema inicial para Supabase (generado desde backend/app/models.py)
--
-- Pensado para convivir con otras aplicaciones en el mismo proyecto Supabase:
--   * Todo vive en el esquema propio `gestoria`, NO expuesto a la API REST pública
--     (PostgREST solo publica `public`/`graphql_public`), y sin permisos para
--     anon / authenticated / public.
--   * La API conecta con el rol dedicado `gestoria_api` (solo DML, sin DDL).
--     Se crea SIN LOGIN: se activa al ponerle contraseña (ver final del fichero).
--   * RLS activado y forzado como segunda barrera.
--   * El login NO usa Supabase Auth (lo gestiona la API), así que no crea usuarios
--     en auth.users ni dispara triggers de otras aplicaciones.
--   * Fotos en un bucket PRIVADO sin políticas: solo accesible con la service_role.
-- =====================================================================

create schema if not exists gestoria;
revoke all on schema gestoria from public, anon, authenticated;
set local search_path to gestoria;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'gestoria_api') then
    create role gestoria_api nologin noinherit;
  end if;
end $$;
alter role gestoria_api set search_path to gestoria;

-- ---------- Tablas ----------
create type tipo_cliente as enum ('autonomo', 'sociedad');
create type rol_usuario as enum ('gestor', 'cliente');
create type estado_factura as enum ('pendiente', 'validada', 'contabilizada', 'rechazada');
create type origen_factura as enum ('movil', 'gestoria');
create table clientes (
	id SERIAL NOT NULL, 
	nif VARCHAR(20) NOT NULL, 
	razon_social VARCHAR(200) NOT NULL, 
	tipo tipo_cliente NOT NULL, 
	email VARCHAR(160), 
	telefono VARCHAR(30), 
	direccion VARCHAR(255), 
	iban VARCHAR(34), 
	regimen_iva VARCHAR(40) NOT NULL, 
	serie_venta VARCHAR(10) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	notas TEXT, 
	creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_clientes_nif ON clientes (nif);
create table asientos (
	id SERIAL NOT NULL, 
	cliente_id INTEGER NOT NULL, 
	ejercicio INTEGER NOT NULL, 
	numero INTEGER NOT NULL, 
	fecha DATE NOT NULL, 
	concepto VARCHAR(255) NOT NULL, 
	origen VARCHAR(20) NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_asiento_numero UNIQUE (cliente_id, ejercicio, numero), 
	FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE
);
CREATE INDEX ix_asientos_fecha ON asientos (fecha);
CREATE INDEX ix_asientos_cliente_id ON asientos (cliente_id);
create table usuarios (
	id SERIAL NOT NULL, 
	auth_uid VARCHAR(36), 
	email VARCHAR(160) NOT NULL, 
	nombre VARCHAR(160) NOT NULL, 
	password_hash VARCHAR(255), 
	fallos_login INTEGER NOT NULL, 
	bloqueado_hasta TIMESTAMP WITHOUT TIME ZONE, 
	rol rol_usuario NOT NULL, 
	cliente_id INTEGER, 
	activo BOOLEAN NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX ix_usuarios_email ON usuarios (email);
CREATE UNIQUE INDEX ix_usuarios_auth_uid ON usuarios (auth_uid);
create table apuntes (
	id SERIAL NOT NULL, 
	asiento_id INTEGER NOT NULL, 
	cuenta VARCHAR(12) NOT NULL, 
	descripcion VARCHAR(255) NOT NULL, 
	debe NUMERIC(14, 2) NOT NULL, 
	haber NUMERIC(14, 2) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(asiento_id) REFERENCES asientos (id) ON DELETE CASCADE
);
CREATE INDEX ix_apuntes_cuenta ON apuntes (cuenta);
CREATE INDEX ix_apuntes_asiento_id ON apuntes (asiento_id);
create table auditoria (
	id SERIAL NOT NULL, 
	usuario_id INTEGER, 
	accion VARCHAR(60) NOT NULL, 
	entidad VARCHAR(40), 
	entidad_id INTEGER, 
	detalle VARCHAR(255), 
	ip VARCHAR(64), 
	fecha TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id) ON DELETE SET NULL
);
CREATE INDEX ix_auditoria_usuario_id ON auditoria (usuario_id);
CREATE INDEX ix_auditoria_fecha ON auditoria (fecha);
create table facturas_compra (
	cliente_id INTEGER NOT NULL, 
	proveedor_nif VARCHAR(20), 
	proveedor_nombre VARCHAR(200), 
	cuenta_gasto VARCHAR(10) NOT NULL, 
	asiento_id INTEGER, 
	id SERIAL NOT NULL, 
	numero VARCHAR(40), 
	fecha DATE, 
	base_imponible NUMERIC(14, 2) NOT NULL, 
	tipo_iva NUMERIC(5, 2) NOT NULL, 
	cuota_iva NUMERIC(14, 2) NOT NULL, 
	tipo_irpf NUMERIC(5, 2) NOT NULL, 
	cuota_irpf NUMERIC(14, 2) NOT NULL, 
	total NUMERIC(14, 2) NOT NULL, 
	estado estado_factura NOT NULL, 
	origen origen_factura NOT NULL, 
	imagen_path VARCHAR(255), 
	concepto VARCHAR(255), 
	notas TEXT, 
	motivo_rechazo VARCHAR(255), 
	conciliada BOOLEAN NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE, 
	FOREIGN KEY(asiento_id) REFERENCES asientos (id) ON DELETE SET NULL
);
CREATE INDEX ix_facturas_compra_estado ON facturas_compra (estado);
CREATE INDEX ix_facturas_compra_fecha ON facturas_compra (fecha);
CREATE INDEX ix_facturas_compra_cliente_id ON facturas_compra (cliente_id);
create table facturas_venta (
	cliente_id INTEGER NOT NULL, 
	destinatario_nif VARCHAR(20), 
	destinatario_nombre VARCHAR(200), 
	cuenta_ingreso VARCHAR(10) NOT NULL, 
	asiento_id INTEGER, 
	id SERIAL NOT NULL, 
	numero VARCHAR(40), 
	fecha DATE, 
	base_imponible NUMERIC(14, 2) NOT NULL, 
	tipo_iva NUMERIC(5, 2) NOT NULL, 
	cuota_iva NUMERIC(14, 2) NOT NULL, 
	tipo_irpf NUMERIC(5, 2) NOT NULL, 
	cuota_irpf NUMERIC(14, 2) NOT NULL, 
	total NUMERIC(14, 2) NOT NULL, 
	estado estado_factura NOT NULL, 
	origen origen_factura NOT NULL, 
	imagen_path VARCHAR(255), 
	concepto VARCHAR(255), 
	notas TEXT, 
	motivo_rechazo VARCHAR(255), 
	conciliada BOOLEAN NOT NULL, 
	creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_venta_numero UNIQUE (cliente_id, numero), 
	FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE, 
	FOREIGN KEY(asiento_id) REFERENCES asientos (id) ON DELETE SET NULL
);
CREATE INDEX ix_facturas_venta_cliente_id ON facturas_venta (cliente_id);
CREATE INDEX ix_facturas_venta_fecha ON facturas_venta (fecha);
CREATE INDEX ix_facturas_venta_estado ON facturas_venta (estado);
create table movimientos_banco (
	id SERIAL NOT NULL, 
	cliente_id INTEGER NOT NULL, 
	fecha DATE NOT NULL, 
	concepto VARCHAR(255) NOT NULL, 
	importe NUMERIC(14, 2) NOT NULL, 
	conciliado BOOLEAN NOT NULL, 
	factura_compra_id INTEGER, 
	factura_venta_id INTEGER, 
	asiento_id INTEGER, 
	creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE, 
	FOREIGN KEY(factura_compra_id) REFERENCES facturas_compra (id) ON DELETE SET NULL, 
	FOREIGN KEY(factura_venta_id) REFERENCES facturas_venta (id) ON DELETE SET NULL, 
	FOREIGN KEY(asiento_id) REFERENCES asientos (id) ON DELETE SET NULL
);
CREATE INDEX ix_movimientos_banco_conciliado ON movimientos_banco (conciliado);
CREATE INDEX ix_movimientos_banco_cliente_id ON movimientos_banco (cliente_id);
CREATE INDEX ix_movimientos_banco_fecha ON movimientos_banco (fecha);

-- ---------- Privilegios ----------
revoke all on all tables in schema gestoria from public, anon, authenticated;
revoke all on all sequences in schema gestoria from public, anon, authenticated;
grant usage on schema gestoria to gestoria_api;
grant select, insert, update, delete on all tables in schema gestoria to gestoria_api;
grant usage, select on all sequences in schema gestoria to gestoria_api;
-- auditoría: solo añadir, nunca modificar ni borrar
revoke update, delete on auditoria from gestoria_api;

-- ---------- Row Level Security ----------
alter table clientes enable row level security;
alter table clientes force row level security;
create policy api_clientes on clientes for all to gestoria_api using (true) with check (true);
alter table asientos enable row level security;
alter table asientos force row level security;
create policy api_asientos on asientos for all to gestoria_api using (true) with check (true);
alter table usuarios enable row level security;
alter table usuarios force row level security;
create policy api_usuarios on usuarios for all to gestoria_api using (true) with check (true);
alter table apuntes enable row level security;
alter table apuntes force row level security;
create policy api_apuntes on apuntes for all to gestoria_api using (true) with check (true);
alter table auditoria enable row level security;
alter table auditoria force row level security;
create policy api_auditoria on auditoria for all to gestoria_api using (true) with check (true);
alter table facturas_compra enable row level security;
alter table facturas_compra force row level security;
create policy api_facturas_compra on facturas_compra for all to gestoria_api using (true) with check (true);
alter table facturas_venta enable row level security;
alter table facturas_venta force row level security;
create policy api_facturas_venta on facturas_venta for all to gestoria_api using (true) with check (true);
alter table movimientos_banco enable row level security;
alter table movimientos_banco force row level security;
create policy api_movimientos_banco on movimientos_banco for all to gestoria_api using (true) with check (true);

-- ---------- Storage: bucket privado ----------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('gestoria-facturas', 'gestoria-facturas', false, 10485760,
        array['image/jpeg','image/png','image/webp','image/heic','application/pdf'])
on conflict (id) do update set public = false;

-- ---------- Activar el rol de la API (EJECUTAR A MANO, con tu contraseña) ----------
-- alter role gestoria_api with login password 'UNA_CONTRASEÑA_LARGA_Y_ALEATORIA';
