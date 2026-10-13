-- ============================================================================
-- BANCO DE SANGRE "HEMOVIDA"
-- SCRIPT DE AJUSTES Y MIGRACIÓN DDL PARA LOS CICLOS 1 Y 2 (CU01 - CU23)
-- ============================================================================

-- 1. Soporte de Seguridad y Bloqueo Temporal (CU01 / CU02)
ALTER TABLE "public"."usuario"
    ADD COLUMN IF NOT EXISTS "intentosfallidos" INT DEFAULT 0 NOT NULL,
    ADD COLUMN IF NOT EXISTS "fechabloqueohasta" TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS "totalbloqueosrecibidos" INT DEFAULT 0 NOT NULL;

ALTER TABLE "public"."usuario" DROP CONSTRAINT IF EXISTS "usuario_estado_check";
ALTER TABLE "public"."usuario" ADD CONSTRAINT "usuario_estado_check"
    CHECK ("estado" IN ('Activo', 'Inactivo', 'Bloqueado', 'Bloqueado Temporal'));

-- 2. Trazabilidad Triaje -> Extracción (CU12)
ALTER TABLE "public"."extracciondonacion"
    ADD COLUMN IF NOT EXISTS "idtriaje" INT UNIQUE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_extraccion_triaje'
    ) THEN
        ALTER TABLE "public"."extracciondonacion"
            ADD CONSTRAINT "fk_extraccion_triaje"
            FOREIGN KEY ("idtriaje") REFERENCES "public"."triajeclinico"("idtriaje") ON DELETE RESTRICT;
    END IF;
END $$;

-- 3. Normalización del Grupo Sanguíneo en Receptor
ALTER TABLE "public"."receptor"
    ADD COLUMN IF NOT EXISTS "idgrupo" INT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_receptor_grupo'
    ) THEN
        ALTER TABLE "public"."receptor"
            ADD CONSTRAINT "fk_receptor_grupo"
            FOREIGN KEY ("idgrupo") REFERENCES "public"."gruposanguineo"("idgrupo") ON DELETE RESTRICT;
    END IF;
END $$;

-- 4. Trazabilidad Compromiso de Reposición -> Extracción (CU20)
ALTER TABLE "public"."compromisodonacion"
    ADD COLUMN IF NOT EXISTS "idextraccion" INT UNIQUE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_compromiso_extraccion'
    ) THEN
        ALTER TABLE "public"."compromisodonacion"
            ADD CONSTRAINT "fk_compromiso_extraccion"
            FOREIGN KEY ("idextraccion") REFERENCES "public"."extracciondonacion"("idextraccion") ON DELETE SET NULL;
    END IF;
END $$;

-- 5. Control de Despacho Único y Bajas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_detalledespacho_ejemplar'
    ) THEN
        ALTER TABLE "public"."detalledespacho"
            ADD CONSTRAINT "uq_detalledespacho_ejemplar" UNIQUE ("idejemplarbolsa");
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_baja_origen_xor'
    ) THEN
        ALTER TABLE "public"."bajainventario"
            ADD CONSTRAINT "chk_baja_origen_xor" CHECK (
                ("idunidadmadre" IS NOT NULL AND "idejemplarbolsa" IS NULL) OR
                ("idunidadmadre" IS NULL AND "idejemplarbolsa" IS NOT NULL)
            );
    END IF;
END $$;

-- 6. Flag Autólogo en Almacén (CU21)
ALTER TABLE "public"."ejemplarbolsa"
    ADD COLUMN IF NOT EXISTS "esexclusivoautologo" BOOLEAN DEFAULT FALSE NOT NULL;

-- 7. Unificación de Inmunohematología en analisisinmunohematologico (CU14)
ALTER TABLE "public"."analisisinmunohematologico"
    ADD COLUMN IF NOT EXISTS "fasesalina" VARCHAR(30),
    ADD COLUMN IF NOT EXISTS "fasetermica" VARCHAR(30),
    ADD COLUMN IF NOT EXISTS "dictameninmunohematologico" VARCHAR(100);

-- Eliminación de la tabla redundante 'pruebainmunohematologica'
DROP TABLE IF EXISTS "public"."pruebainmunohematologica" CASCADE;
