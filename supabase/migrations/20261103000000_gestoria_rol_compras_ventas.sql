-- =====================================================================
-- Gestoría · rol combinado "compras y ventas" (una persona sube las dos cosas)
-- Aditiva: solo añade un valor al enum de roles.
-- =====================================================================
alter type gestoria.rol_usuario add value if not exists 'cliente_compras_ventas';
