import React, { useState } from "react";
import { request } from "../../services/cloudApi";
import {
  Row,
  Form,
  Panel,
  Table,
  ages,
  roles,
  options,
  personFields,
  useResource,
  ResourceNotice,
} from "./ui";
export function InventoryPage({
  operations,
  version,
}: {
  operations: Row;
  version: number;
}) {
  const [query, setQuery] = useState("");
  const resource = useResource<Row>(
    "stock/monitor-semaforo/" + query,
    { tarjetas: [], cola_fefo: [] },
    version,
  );
  return (
    <>
      <Panel title="Disponibilidad por grupo y componente">
        <ResourceNotice {...resource} />
        <Form
          fields={[
            {
              name: "categoriaetaria",
              label: "Categoría",
              options: [{ value: "Todos", label: "Todos" }, ...ages],
              value: "Todos",
            },
            {
              name: "componente",
              label: "Componente",
              options: options([
                "Todos",
                "Concentrado de Globulos Rojos",
                "Plasma Fresco Congelado",
                "Concentrado Plaquetario",
              ]),
              value: "Todos",
            },
          ]}
          submit="Filtrar"
          onSubmit={async (data) => {
            setQuery(
              "?" +
                new URLSearchParams({
                  categoriaetaria: data.categoriaetaria,
                  ...(data.componente === "Todos"
                    ? {}
                    : { componente: data.componente }),
                }),
            );
          }}
        />
        <div className="hv-stock-grid">
          {resource.data.tarjetas.map((s: Row) => (
            <article key={s.idparametro}>
              <span className={`hv-badge ${s.semaforo}`}>{s.semaforo}</span>
              <strong>{s.grupo_sanguineo}</strong>
              <h3>{s.tipocomponente}</h3>
              <p>{s.categoriaetaria}</p>
              <b>{s.stock_disponible} unidades</b>
              <small>
                Mínimo: {s.stock_minimo_seguridad} · Crítico:{" "}
                {s.stock_critico_alerta}
              </small>
            </article>
          ))}
        </div>
        {!resource.data.tarjetas.length && !resource.loading && (
          <p className="hv-muted">No hay parámetros para esta selección.</p>
        )}
      </Panel>
      <Panel
        title="Prioridad por vencimiento"
        subtitle="Unidades de stock general que vencen en los próximos siete días."
      >
        <Table
          rows={resource.data.cola_fefo}
          columns={[
            ["codigo", "Código"],
            ["componente", "Componente"],
            ["categoriaetaria", "Categoría"],
            ["fechacaducidad", "Vencimiento"],
            ["dias_restantes", "Días restantes"],
          ]}
        />
      </Panel>
      <Panel title="Unidades registradas">
        <Table
          rows={operations.bolsas}
          columns={[
            ["codigoejemplark", "Código"],
            ["tipocomponente", "Componente"],
            ["categoriaetaria", "Categoría"],
            ["estadobolsak", "Estado"],
            ["esexclusivoautologo", "Exclusiva autóloga"],
          ]}
        />
      </Panel>
    </>
  );
}
export function AdminPage({
  catalog,
  version,
  changed,
}: {
  catalog: Row;
  version: number;
  changed: () => void;
}) {
  const users = useResource<Row[]>("usuarios/", [], version),
    applications = useResource<Row[]>("personal/solicitudes/", [], version);
  const params = useResource<Row[]>("stock/parametros/", [], version);
  const [error, setError] = useState("");
  const mutate = async (path: string, data: Row, method?: string) => {
    await request(path, data, method);
    changed();
  };
  const action = async (path: string, data: Row, method?: string) => {
    try {
      await mutate(path, data, method);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <>
      {error && (
        <p className="hv-error" role="alert">
          {error}
        </p>
      )}
      <Panel title="Cuentas institucionales">
        <ResourceNotice {...users} />
        <Table
          rows={users.data}
          columns={[
            ["username", "Usuario"],
            ["email", "Correo"],
            ["estado", "Estado"],
          ]}
          actions={(u) => (
            <>
              {u.estado === "Bloqueado Temporal" && (
                <button
                  onClick={() =>
                    void action(`usuarios/${u.idUsuario}/desbloquear/`, {})
                  }
                >
                  Desbloquear
                </button>
              )}
              <select
                aria-label={`Estado de ${u.username}`}
                value={
                  ["Activo", "Inactivo", "Bloqueado"].includes(u.estado)
                    ? u.estado
                    : ""
                }
                onChange={(e) =>
                  void action(
                    `usuarios/${u.idUsuario}/estado/`,
                    { estado: e.target.value },
                    "PATCH",
                  )
                }
              >
                <option value="" disabled>
                  Bloqueo temporal
                </option>
                {["Activo", "Inactivo", "Bloqueado"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </>
          )}
        />
      </Panel>
      <Panel title="Solicitudes de cargos">
        <ResourceNotice {...applications} />
        <Table
          rows={applications.data}
          columns={[
            ["usuario", "Usuario"],
            ["cargo", "Cargo"],
            ["codigo", "Perfil solicitado"],
            ["registroprofesional", "Matrícula"],
            ["pendiente", "Pendiente"],
          ]}
          actions={(r) =>
            r.pendiente && (
              <>
                <button
                  onClick={() =>
                    void action(`personal/solicitudes/${r.id}/resolver/`, {
                      aprobar: true,
                    })
                  }
                >
                  Aprobar
                </button>
                <button
                  onClick={() =>
                    void action(`personal/solicitudes/${r.id}/resolver/`, {
                      aprobar: false,
                    })
                  }
                >
                  Rechazar
                </button>
              </>
            )
          }
        />
      </Panel>
      <Panel title="Alta de personal de salud">
        <Form
          fields={[
            ...personFields,
            { name: "cargo", label: "Cargo" },
            { name: "registroProfesional", label: "Matrícula profesional" },
            {
              name: "codigoRolAsignar",
              label: "Perfil institucional",
              options: roles,
            },
          ]}
          submit="Crear cuenta"
          onSubmit={(data) => mutate("personal/crear/", data)}
        />
      </Panel>
      <div className="hv-grid">
        <Panel title="Crear parámetro de stock">
          <Form
            fields={[
              {
                name: "idgrupo",
                label: "Grupo",
                options: catalog.grupos.map((g: Row) => ({
                  value: g.idgrupo,
                  label: `${g.grupoabo} ${g.factorrh}`,
                })),
              },
              {
                name: "tipocomponente",
                label: "Componente",
                options: options(catalog.componentes),
              },
              { name: "categoriaetaria", label: "Categoría", options: ages },
              {
                name: "stockminimoseguridad",
                label: "Mínimo de seguridad",
                type: "number",
                min: 1,
              },
              {
                name: "stockcriticoalerta",
                label: "Umbral crítico",
                type: "number",
                min: 0,
              },
            ]}
            submit="Crear parámetro"
            onSubmit={(data) => mutate("stock/parametros/", data)}
          />
        </Panel>
        <Panel title="Actualizar umbrales">
          <ResourceNotice {...params} />
          <Form
            fields={[
              {
                name: "idparametro",
                label: "Parámetro",
                options: params.data.map((s: Row) => ({
                  value: s.idparametro,
                  label: `${s.grupoABO} ${s.factorRh} · ${s.tipocomponente} · ${s.categoriaetaria}`,
                })),
              },
              {
                name: "stockminimoseguridad",
                label: "Mínimo de seguridad",
                type: "number",
                min: 1,
              },
              {
                name: "stockcriticoalerta",
                label: "Umbral crítico",
                type: "number",
                min: 0,
              },
            ]}
            submit="Actualizar umbrales"
            onSubmit={(data) =>
              mutate(`stock/parametros/${data.idparametro}/`, data, "PUT")
            }
          />
        </Panel>
      </div>
    </>
  );
}
export function AuditPage() {
  const [audit, setAudit] = useState<Row | null>(null);
  return (
    <Panel title="Bitácora de operaciones">
      <Form
        fields={[
          { name: "q", label: "Texto o C.I.", required: false },
          {
            name: "id_usuario",
            label: "ID de usuario",
            type: "number",
            min: 1,
            required: false,
          },
          { name: "tabla_afectada", label: "Tabla afectada", required: false },
          {
            name: "fecha_inicio",
            label: "Desde",
            type: "date",
            required: false,
          },
          { name: "fecha_fin", label: "Hasta", type: "date", required: false },
          {
            name: "fuera_turno",
            label: "Solo horario nocturno (19:00 a 07:00)",
            type: "checkbox",
            required: false,
          },
        ]}
        submit="Consultar bitácora"
        onSubmit={async (data) => {
          const q = new URLSearchParams(
            Object.entries(data)
              .filter(([, v]) => v !== "" && v !== false)
              .map(([k, v]) => [k, String(v)]),
          );
          setAudit(await request(`auditoria/?${q}`));
        }}
      />
      {audit && (
        <>
          <p className="hv-muted">
            {audit.totalRegistros} eventos encontrados. Se muestran hasta 1000;
            acota las fechas para consultar más.
          </p>
          <Table
            rows={audit.eventos}
            columns={[
              ["fechaHora", "Fecha"],
              ["funcionario", "Usuario"],
              ["rolActivo", "Perfil activo"],
              ["accionRealizada", "Acción"],
              ["tablaAfectada", "Tabla"],
              ["ipOrigen", "IP"],
            ]}
          />
        </>
      )}
    </Panel>
  );
}
export function KpiPage({ version }: { version: number }) {
  const [query, setQuery] = useState("");
  const resource = useResource<Row | null>(
      "stock/kpis-gerenciales/" + query,
      null,
      version,
    ),
    k = resource.data;
  return (
    <Panel title="Indicadores de gestión">
      <Form
        fields={[
          { name: "fecha_inicio", label: "Desde", type: "date" },
          { name: "fecha_fin", label: "Hasta", type: "date" },
        ]}
        submit="Consultar período"
        onSubmit={async (data) => setQuery("?" + new URLSearchParams(data))}
      />
      <ResourceNotice {...resource} />
      {k && (
        <>
          {k.sin_actividad && (
            <p className="hv-muted">
              No se registraron movimientos en este período.
            </p>
          )}
          <div className="hv-stats">
            {[
              ["tasa_efectividad_citas", "Efectividad de citas"],
              ["tasa_positividad_serologica", "Positividad serológica"],
              ["ocupacion_camaras_porcentaje", "Ocupación de cámaras"],
              ["indice_reposicion_cumplida", "Reposición cumplida"],
            ].map(([key, label]) => (
              <div key={key}>
                <strong>{k.kpis[key]}%</strong>
                <span>{label}</span>
              </div>
            ))}
          </div>
          <p className="hv-muted">
            Citas: {k.kpis.total_citas} · Atendidas: {k.kpis.citas_atendidas} ·
            Inasistencias: {k.kpis.inasistencias} · Análisis:{" "}
            {k.kpis.total_serologias} · Aptos: {k.kpis.serologias_aptas} ·
            Reactivos: {k.kpis.serologias_reactivas} · Reposiciones:{" "}
            {k.kpis.total_reposiciones} · Liquidadas:{" "}
            {k.kpis.reposiciones_liquidadas}
          </p>
          <h3>Cámaras frías</h3>
          <Table
            rows={k.camaras_detalle}
            columns={[
              ["compartimento", "Compartimento"],
              ["equipo", "Equipo"],
              ["temperatura_c", "Temperatura °C"],
              ["ocupadas", "Ocupación"],
              ["maxima", "Capacidad"],
              ["porcentaje_uso", "Uso %"],
            ]}
          />
          <h3>Demanda hospitalaria</h3>
          <Table
            rows={k.ranking_hospitales}
            columns={[
              ["hospital", "Institución"],
              ["total_solicitudes", "Solicitudes"],
              ["bolsas_requeridas", "Solicitadas"],
              ["bolsas_entregadas", "Entregadas"],
            ]}
          />
        </>
      )}
    </Panel>
  );
}
