-- =====================================================================
-- Gestoría · albaranes de proveedor + lectura automática de documentos
-- Aditiva: no modifica datos existentes.
-- =====================================================================
set local search_path to gestoria;

create type estado_albaran as enum ('pendiente', 'revisado', 'facturado', 'rechazado');

create table albaranes (
	id SERIAL NOT NULL, 
	cliente_id INTEGER NOT NULL, 
	proveedor_nif VARCHAR(20), 
	proveedor_nombre VARCHAR(200), 
	numero VARCHAR(40), 
	fecha DATE, 
	base_imponible NUMERIC(14, 2) NOT NULL, 
	tipo_iva NUMERIC(5, 2), 
	total NUMERIC(14, 2), 
	estado estado_albaran NOT NULL, 
	origen origen_factura NOT NULL, 
	imagen_path VARCHAR(255), 
	notas TEXT, 
	motivo_rechazo VARCHAR(255), 
	factura_compra_id INTEGER, 
	extraccion_confianza VARCHAR(10), 
	extraccion_avisos TEXT, 
	creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(cliente_id) REFERENCES clientes (id) ON DELETE CASCADE, 
	FOREIGN KEY(factura_compra_id) REFERENCES facturas_compra (id) ON DELETE SET NULL
);
CREATE INDEX ix_albaranes_proveedor_nif ON albaranes (proveedor_nif);
CREATE INDEX ix_albaranes_factura_compra_id ON albaranes (factura_compra_id);
CREATE INDEX ix_albaranes_cliente_id ON albaranes (cliente_id);
CREATE INDEX ix_albaranes_fecha ON albaranes (fecha);
CREATE INDEX ix_albaranes_estado ON albaranes (estado);

-- Resultado de la lectura automática (OCR local) en las facturas
alter table facturas_compra add column extraccion_confianza varchar(10), add column extraccion_avisos text;
alter table facturas_venta  add column extraccion_confianza varchar(10), add column extraccion_avisos text;

-- Permisos y RLS igual que el resto del esquema
revoke all on albaranes from public, anon, authenticated;
revoke all on sequence albaranes_id_seq from public, anon, authenticated;
grant select, insert, update, delete on albaranes to gestoria_api;
grant usage, select on sequence albaranes_id_seq to gestoria_api;
alter table albaranes enable row level security;
alter table albaranes force row level security;
create policy api_albaranes on albaranes for all to gestoria_api using (true) with check (true);
