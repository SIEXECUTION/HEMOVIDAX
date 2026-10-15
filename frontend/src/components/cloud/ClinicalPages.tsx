import React, { useState } from "react";
import { request } from "../../services/cloudApi";
import {
  Row,
  Field,
  ages,
  options,
  Form,
  Panel,
  Table,
  useResource,
  ResourceNotice,
} from "./ui";
export function ClinicalPages({
  tab,
  role,
  catalog,
  operations,
  version,
  changed,
}: {
  tab: string;
  role: string;
  catalog: Row;
  operations: Row;
  version: number;
  changed: (message?: string) => void;
}) {
  const [found, setFound] = useState<Row | null>(null),
    [error, setError] = useState("");
  const appointments = useResource<Row[]>("donantes/citas/", [], version);
  const can = (...values: string[]) =>
    role === "ADMIN" || values.includes(role);
  const person: Field = {
    name: "idpersona",
    label: "Persona",
    options: operations.personas.map((p: Row) => ({
      value: p.idpersona,
      label: `${p.nombres} ${p.apellidos} · ${p.ci}`,
    })),
  };
  const groups = catalog.grupos.map((g: Row) => ({
    value: g.idgrupo,
    label: `${g.grupoabo}${g.factorrh === "Positivo" ? "+" : "-"}`,
  }));
  const units = operations.unidades.map((u: Row) => ({
    value: u.idunidadmadre,
    label: `${u.codigobolsamadre} · ${u.estadoliberacion}`,
  }));
  const rooms = catalog.ubicaciones.map((r: Row) => ({
    value: r.idubicacion,
    label: `${r.identificadorcompartimento} (${r.capacidadocupada}/${r.capacidadmaxima})`,
  }));
  const mutate = async (path: string, data: Row) => {
    await request(path, data);
    changed();
  };
  if (tab === "admision")
    return (
      <>
        <Panel title="Buscar donante o postulante">
          <Form
            fields={[{ name: "ci", label: "C.I. o código de carnet" }]}
            submit="Buscar"
            onSubmit={async (data) =>
              setFound(
                await request(
                  `donantes/${encodeURIComponent(data.ci)}/carnet/`,
                ),
              )
            }
          />
          {found && (
            <div className="hv-search-result">
              <h3>{found.nombre_completo}</h3>
              <p>
                {found.carnet_codigo} · {found.grupo_sanguineo}
              </p>
              <p>
                {found.elegibilidad.motivo ||
                  "Sin impedimento por descanso o diferimiento."}
              </p>
            </div>
          )}
        </Panel>
        <Panel title="Confirmar asistencia">
          <ResourceNotice {...appointments} />
          <Table
            rows={appointments.data.filter(
              (a) => a.estadocita === "Programada",
            )}
            columns={[
              ["persona", "Persona"],
              ["ci", "C.I."],
              ["fechahoraprogramada", "Cita"],
              ["asistenciaconfirmada", "Asistencia"],
            ]}
            actions={(r) =>
              can("PERS_COLECTA") && (
                <button
                  onClick={async () => {
                    try {
                      const result = await request(
                        `donantes/citas/${r.idcita}/admision/`,
                        {},
                      );
                      changed(result.mensaje);
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Confirmar / verificar pase
                </button>
              )
            }
          />
          {error && (
            <p role="alert" className="hv-error">
              {error}
            </p>
          )}
        </Panel>
      </>
    );
  if (tab === "clinica")
    return (
      <>
        <div className="hv-grid">
          {can("DOC_TRIAJE") && (
            <Panel title="Evaluación de triaje">
              <Form
                fields={[
                  person,
                  {
                    name: "pesokg",
                    label: "Peso (kg)",
                    type: "number",
                    min: 1,
                  },
                  {
                    name: "presionsistolica",
                    label: "Presión sistólica (mmHg)",
                    type: "number",
                    min: 1,
                  },
                  {
                    name: "presiondiastolica",
                    label: "Presión diastólica (mmHg)",
                    type: "number",
                    min: 1,
                  },
                  {
                    name: "hemoglobina",
                    label: "Hemoglobina (g/dl)",
                    type: "number",
                    min: 1,
                  },
                  {
                    name: "temperatura",
                    label: "Temperatura (°C)",
                    type: "number",
                    min: 30,
                    max: 45,
                  },
                  {
                    name: "motivodiferimiento",
                    label: "Motivo de rechazo, si corresponde",
                    required: false,
                  },
                  {
                    name: "diasinhabilitacion",
                    label: "Días de diferimiento",
                    type: "number",
                    value: "30",
                    min: 1,
                  },
                  {
                    name: "definitivo",
                    label: "Diferimiento definitivo",
                    type: "checkbox",
                    required: false,
                  },
                ]}
                submit="Registrar triaje"
                onSubmit={(data) => mutate("donantes/triaje/", data)}
              />
            </Panel>
          )}
          {can("PERS_COLECTA") && (
            <Panel title="Extracción y consentimiento">
              <Form
                fields={[
                  { ...person, name: "idpersonadonante" },
                  {
                    name: "idtriaje",
                    label: "Triaje aprobado",
                    options: operations.triajes
                      .filter((t: Row) => t.resultadoaptitud === "Apto")
                      .map((t: Row) => ({
                        value: t.idtriaje,
                        label: `Triaje ${t.idtriaje} · Persona ${t.idposibledonador}`,
                      })),
                  },
                  {
                    name: "idgrupo",
                    label: "Grupo sanguíneo",
                    options: groups,
                  },
                  {
                    name: "volumenml",
                    label: "Volumen extraído (ml)",
                    type: "number",
                    min: 1,
                    max: 1000,
                  },
                  {
                    name: "brazo",
                    label: "Brazo",
                    options: options(["Derecho", "Izquierdo"]),
                  },
                  {
                    name: "firmadigital",
                    label: "Firma / constancia de consentimiento",
                  },
                  {
                    name: "declaracionjuradaaceptada",
                    label: "Declaración jurada y consentimiento aceptados",
                    type: "checkbox",
                  },
                ]}
                submit="Registrar extracción"
                onSubmit={(data) => mutate("donantes/flebotomia/", data)}
              />
            </Panel>
          )}
        </div>
        <Panel title="Refrigerio e incentivos">
          <Table
            rows={operations.extracciones}
            columns={[
              ["persona", "Persona"],
              ["codigoextraccion", "Extracción"],
              ["refrigerioentregado", "Refrigerio entregado"],
            ]}
          />
          {can("PERS_COLECTA") && (
            <Form
              fields={[
                {
                  name: "idextraccion",
                  label: "Extracción concluida",
                  options: operations.extracciones
                    .filter((e: Row) => !e.refrigerioentregado)
                    .map((e: Row) => ({
                      value: e.idextraccion,
                      label: `${e.persona} · ${e.codigoextraccion}`,
                    })),
                },
                {
                  name: "tipoarticulo",
                  label: "Artículo entregado junto al refrigerio",
                  value: "Refrigerio nutricional",
                },
              ]}
              submit="Confirmar entrega de refrigerio"
              onSubmit={(data) =>
                mutate(
                  `donantes/extracciones/${data.idextraccion}/refrigerio/`,
                  { tipoarticulo: data.tipoarticulo },
                )
              }
            />
          )}
        </Panel>
      </>
    );
  if (tab === "laboratorio")
    return (
      <>
        <div className="hv-grid">
          <Panel title="Inmunohematología">
            <Form
              fields={[
                person,
                {
                  name: "idunidadmadre",
                  label: "Unidad madre (opcional en evaluación previa)",
                  options: units,
                  required: false,
                },
                {
                  name: "grupoaboconfirmado",
                  label: "Grupo ABO confirmado",
                  options: options(["A", "B", "AB", "O"]),
                },
                {
                  name: "factorrhconfirmado",
                  label: "Factor Rh",
                  options: options(["Positivo", "Negativo"]),
                },
                { name: "pruebacoombsdirecta", label: "Coombs directa" },
                { name: "pruebacoombsindirecta", label: "Coombs indirecta" },
                {
                  name: "rastreoanticuerposirregulares",
                  label: "Anticuerpos irregulares",
                },
                {
                  name: "dictameninmunohematologico",
                  label: "Dictamen",
                  options: options(["Apto", "No Apto"]),
                },
              ]}
              submit="Guardar análisis"
              onSubmit={async (data) => {
                if (!data.idunidadmadre) delete data.idunidadmadre;
                await mutate("inventario/laboratorio/hematologia/", data);
              }}
            />
          </Panel>
          <Panel title="Tamizaje serológico">
            <Form
              fields={[
                {
                  name: "idunidadmadre",
                  label: "Unidad madre",
                  options: units,
                },
                ...[
                  "vih",
                  "chagas",
                  "hepatitisb",
                  "hepatitisc",
                  "sifilis",
                  "htlv",
                ].map((name) => ({
                  name: `resultado${name}`,
                  label: name.toUpperCase(),
                  options: options([
                    "No Reactivo",
                    "Reactivo",
                    "Indeterminado",
                  ]),
                })),
              ]}
              submit="Registrar resultados"
              onSubmit={(data) =>
                mutate(
                  `inventario/laboratorio/serologia/${data.idunidadmadre}/`,
                  data,
                )
              }
            />
          </Panel>
        </div>
        <Panel title="Fraccionamiento y almacenamiento">
          <Form
            fields={[
              { name: "idunidadmadre", label: "Unidad madre", options: units },
              {
                name: "categoriaetaria",
                label: "Categoría etaria",
                options: ages,
              },
              ...["gr", "pl", "pq"].map((name, i) => ({
                name,
                label: `Ubicación: ${catalog.componentes[i] || name}`,
                options: rooms,
              })),
            ]}
            submit="Fraccionar unidad"
            onSubmit={(data) =>
              mutate(`stock/fraccionar/${data.idunidadmadre}/`, {
                categoriaetaria: data.categoriaetaria,
                ubicaciones: { gr: data.gr, pl: data.pl, pq: data.pq },
              })
            }
          />
        </Panel>
      </>
    );
  if (tab === "autologa")
    return (
      <>
        <div className="hv-grid">
          {can("DOC_TRIAJE", "MED_SOLICITANTE") && (
            <Panel title="Programar donación autóloga">
              <Form
                fields={[
                  person,
                  {
                    name: "idgrupo",
                    label: "Grupo sanguíneo",
                    options: groups,
                  },
                  {
                    name: "fechahoracita",
                    label: "Cita de extracción",
                    type: "datetime-local",
                  },
                  {
                    name: "fechacirugia",
                    label: "Fecha de cirugía",
                    type: "date",
                  },
                ]}
                submit="Programar protocolo"
                onSubmit={(data) => mutate("stock/autologa/programar/", data)}
              />
            </Panel>
          )}
          {can("BIOQ_INTEGRAL") && (
            <Panel title="Custodia exclusiva">
              <Form
                fields={[
                  {
                    name: "idunidadmadre",
                    label: "Unidad madre del paciente",
                    options: units,
                  },
                ]}
                submit="Reservar para cirugía"
                onSubmit={(data) =>
                  mutate(`stock/autologa/custodiar/${data.idunidadmadre}/`, {})
                }
              />
            </Panel>
          )}
        </div>
        <Panel title="Cirugías registradas">
          <Table
            rows={operations.autologas}
            columns={[
              ["idcitalab", "Protocolo"],
              ["idreceptor", "Paciente"],
              ["fechacirugiaprogramada", "Cirugía"],
              ["estadocita", "Estado"],
            ]}
            actions={(r) =>
              can("DOC_TRIAJE", "MED_SOLICITANTE") &&
              r.estadocita === "Programada" && (
                <button
                  className="hv-danger"
                  onClick={async () => {
                    if (
                      !window.confirm(
                        "¿Confirmas la suspensión definitiva? Las bolsas exclusivas se darán de baja.",
                      )
                    )
                      return;
                    try {
                      await mutate(
                        `stock/autologa/cancelar-cirugia/${r.idreceptor}/`,
                        {},
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Suspensión definitiva
                </button>
              )
            }
          />
          {error && (
            <p className="hv-error" role="alert">
              {error}
            </p>
          )}
        </Panel>
      </>
    );
  return null;
}
