-- =====================================================================
-- Gestoría · roles del cliente, ventas TPV (cierres Z), cierre mensual
-- Aditiva salvo el renombrado del rol 'cliente' -> 'cliente_admin'.
-- =====================================================================
set local search_path to gestoria;

-- Roles: el antiguo "cliente" pasa a ser "cliente_admin"
alter type rol_usuario rename value 'cliente' to 'cliente_admin';
alter type rol_usuario add value if not exists 'cliente_compras';
alter type rol_usuario add value if not exists 'cliente_ventas';

create type estado_cierre as enum ('abierto', 'cerrado', 'liquidado');

alter table clientes add column periodo_iva varchar(12) not null default 'trimestral';

-- Quién subió cada documento (compras/ventas solo ven lo suyo)
alter table facturas_compra add column subido_por_id integer references usuarios (id) on delete set null;
alter table facturas_venta  add column subido_por_id integer references usuarios (id) on delete set null;
alter table albaranes       add column subido_por_id integer references usuarios (id) on delete set null;

create table ventas_tpv (
	id SERIAL NOT NULL, 
	cliente_id INTEGER NOT NULL, 
	fecha DATE, 
	numero_z VARCHAR(30), 
	num_tickets INTEGER, 
	base_imponible NUMERIC(14, 2) NOT NULL, 
	cuota_iva NUMERIC(14, 2) NOT NULL, 
	total NUMERIC(14, 2) NOT NULL, 
	cobro_efectivo NUMERIC(14, 2) NOT NULL, 
	cobro_tarjeta NUMERIC(14, 2) NOT NULL, 
	cuenta_ingreso VARCHAR(10) NOT NULL, 
	estado estado_factura NOT NULL, 
	imagen_path VARCHAR(255), 
	notas TEXT, 
	motivo_rechazo VARCHAR(255), 
	asiento_id INTEGER, 
	extraccion_confianza VARCHAR(10), 
	extraccion_avisos TEXT, 
	subido_por_id INTEGER, 
	creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE, 
	FOREIGN KEY(asiento_id) REFERENCES asientos (id) ON DELETE SET NULL, 
	FOREIGN KEY(subido_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);
CREATE INDEX ix_ventas_tpv_estado ON ventas_tpv (estado);
CREATE INDEX ix_ventas_tpv_fecha ON ventas_tpv (fecha);
CREATE INDEX ix_ventas_tpv_cliente_id ON ventas_tpv (cliente_id);
create table ventas_tpv_iva (
	id SERIAL NOT NULL, 
	venta_id INTEGER NOT NULL, 
	tipo_iva NUMERIC(5, 2) NOT NULL, 
	base NUMERIC(14, 2) NOT NULL, 
	cuota NUMERIC(14, 2) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(venta_id) REFERENCES ventas_tpv (id) ON DELETE CASCADE
);
CREATE INDEX ix_ventas_tpv_iva_venta_id ON ventas_tpv_iva (venta_id);
create table cierres_mes (
	id SERIAL NOT NULL, 
	cliente_id INTEGER NOT NULL, 
	anio INTEGER NOT NULL, 
	mes INTEGER NOT NULL, 
	estado estado_cierre NOT NULL, 
	cerrado_por_id INTEGER, 
	cerrado_en TIMESTAMP WITHOUT TIME ZONE, 
	liquidado_por_id INTEGER, 
	liquidado_en TIMESTAMP WITHOUT TIME ZONE, 
	resumen TEXT, 
	notas TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_cierre_mes UNIQUE (cliente_id, anio, mes), 
	FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE, 
	FOREIGN KEY(cerrado_por_id) REFERENCES usuarios (id) ON DELETE SET NULL, 
	FOREIGN KEY(liquidado_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);
CREATE INDEX ix_cierres_mes_cliente_id ON cierres_mes (cliente_id);

revoke all on ventas_tpv from public, anon, authenticated;
revoke all on sequence ventas_tpv_id_seq from public, anon, authenticated;
grant select, insert, update, delete on ventas_tpv to gestoria_api;
grant usage, select on sequence ventas_tpv_id_seq to gestoria_api;
alter table ventas_tpv enable row level security;
alter table ventas_tpv force row level security;
create policy api_ventas_tpv on ventas_tpv for all to gestoria_api using (true) with check (true);
revoke all on ventas_tpv_iva from public, anon, authenticated;
revoke all on sequence ventas_tpv_iva_id_seq from public, anon, authenticated;
grant select, insert, update, delete on ventas_tpv_iva to gestoria_api;
grant usage, select on sequence ventas_tpv_iva_id_seq to gestoria_api;
alter table ventas_tpv_iva enable row level security;
alter table ventas_tpv_iva force row level security;
create policy api_ventas_tpv_iva on ventas_tpv_iva for all to gestoria_api using (true) with check (true);
revoke all on cierres_mes from public, anon, authenticated;
revoke all on sequence cierres_mes_id_seq from public, anon, authenticated;
grant select, insert, update, delete on cierres_mes to gestoria_api;
grant usage, select on sequence cierres_mes_id_seq to gestoria_api;
alter table cierres_mes enable row level security;
alter table cierres_mes force row level security;
create policy api_cierres_mes on cierres_mes for all to gestoria_api using (true) with check (true);
