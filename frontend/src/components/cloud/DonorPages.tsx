import React, { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Session, request } from "../../services/cloudApi";
import {
  Row,
  Form,
  Panel,
  Table,
  roles,
  useResource,
  ResourceNotice,
} from "./ui";

export function DonorCard({
  personId,
  version,
  view = "all",
}: {
  personId: number;
  version: number;
  view?: "all" | "history" | "card";
}) {
  const resource = useResource<Row | null>(
      `donantes/carnet-digital/${personId}/`,
      null,
      version,
    ),
    c = resource.data;
  const [qr, setQr] = useState("");
  useEffect(() => {
    let cancelled = false;
    setQr("");
    if (c?.qr_validation_string)
      QRCode.toDataURL(c.qr_validation_string, { width: 180, margin: 2 }).then(
        (v) => {
          if (!cancelled) setQr(v);
        },
      );
    return () => {
      cancelled = true;
    };
  }, [c]);
  return (
    <>
      <ResourceNotice {...resource} />
      {c && (
        <>
          {view !== "history" && (
            <div className="hv-grid">
              <Panel title="Tu carnet de donación">
                <div className="hv-card">
                  <div>
                    <span className="hv-eyebrow">
                      {c.esPosibleDonador ? "CARNET PROVISIONAL" : "DONANTE"}
                    </span>
                    <h2>{c.nombre_completo}</h2>
                    <p>C.I. {c.ci}</p>
                    <strong>{c.grupo_sanguineo}</strong>
                    <p>{c.carnet_codigo}</p>
                    {qr && (
                      <a download="carnet-qr.png" href={qr}>
                        Descargar QR
                      </a>
                    )}
                  </div>
                  {qr && <img src={qr} alt="Código QR del carnet" />}
                </div>
              </Panel>
              <Panel title="Tu próxima donación">
                <span
                  className={`hv-badge ${c.esPosibleDonador && c.elegibilidad.semaforo !== "Rojo" ? "Amarillo" : c.elegibilidad.semaforo}`}
                >
                  {c.estado_habilitacion}
                </span>
                <p>
                  {c.elegibilidad.motivo ||
                    "Puedes completar el prefiltro para programar tu evaluación."}
                </p>
                <progress
                  max="100"
                  value={c.elegibilidad.porcentaje_recuperacion}
                />
                <p>
                  Recuperación biológica:{" "}
                  {c.elegibilidad.porcentaje_recuperacion}%
                </p>
                <p>
                  Próxima fecha por descanso: {c.elegibilidad.proxima_fecha}
                </p>
                {c.elegibilidad.suspendido_hasta && (
                  <p>Suspensión hasta: {c.elegibilidad.suspendido_hasta}</p>
                )}
              </Panel>
            </div>
          )}
          {view !== "card" && (
            <>
              <Panel title="Historial de donaciones">
                <Table
                  rows={c.historial_donaciones}
                  columns={[
                    ["codigoextraccion", "Código"],
                    ["fechahora", "Fecha"],
                    ["volumenextraidoml", "Volumen (ml)"],
                    ["brazoextraccion", "Brazo"],
                  ]}
                />
              </Panel>
              <Panel title="Compromisos de reposición">
                <Table
                  rows={c.historial_reposiciones}
                  columns={[
                    ["idcompromiso", "Compromiso"],
                    ["fechacompromiso", "Fecha"],
                    ["estadocompromiso", "Estado"],
                    ["donacionconcretada", "Concretada"],
                  ]}
                />
              </Panel>
            </>
          )}
        </>
      )}
    </>
  );
}

export function Appointments({
  session,
  clinical,
  people,
  version,
  changed,
}: {
  session: Session;
  clinical: boolean;
  people: Row[];
  version: number;
  changed: (message?: string) => void;
}) {
  const appointments = useResource<Row[]>("donantes/citas/", [], version);
  const requirements = useResource<Row[]>("donantes/requisitos/", [], version);
  const [error, setError] = useState("");
  return (
    <>
      <ResourceNotice {...appointments} />
      <Panel title="Citas registradas">
        <Table
          rows={appointments.data.map((a) => ({
            ...a,
            fecha: new Date(a.fechahoraprogramada).toLocaleString("es-BO"),
          }))}
          columns={[
            ["persona", "Persona"],
            ["fecha", "Fecha y hora"],
            ["fase", "Fase"],
            ["estadocita", "Estado"],
            ["asistenciaconfirmada", "Asistencia"],
          ]}
          actions={(r) =>
            r.estadocita === "Programada" &&
            !r.asistenciaconfirmada && (
              <button
                onClick={async () => {
                  try {
                    await request(`donantes/citas/${r.idcita}/cancelar/`, {});
                    changed();
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                Cancelar cita
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
      <Panel
        title="Prefiltro y nueva cita"
        subtitle="Indica si cumples cada requisito del catálogo institucional. La evaluación médica confirma la aptitud final."
      >
        <ResourceNotice {...requirements} />
        <Form
          fields={[
            ...(clinical
              ? [
                  {
                    name: "idpersona",
                    label: "Persona",
                    options: people.map((p) => ({
                      value: p.idpersona,
                      label: `${p.nombres} ${p.apellidos} · ${p.ci}`,
                    })),
                  },
                ]
              : []),
            {
              name: "fechahoraprogramada",
              label: "Fecha y hora",
              type: "datetime-local",
            },
            ...requirements.data.map((r) => ({
              name: `req_${r.idrequisito}`,
              label: r.nombrerequisito,
              options: [
                { value: "true", label: "Sí, cumplo" },
                { value: "false", label: "No cumplo" },
              ],
            })),
          ]}
          submit="Evaluar y agendar"
          onSubmit={async (data) => {
            if (!requirements.data.length)
              throw new Error(
                "No hay requisitos configurados. Contacta al administrador.",
              );
            const result = await request("donantes/citas/", {
              idpersona: clinical
                ? data.idpersona
                : session.account.persona?.idPersona,
              fechahoraprogramada: data.fechahoraprogramada,
              requisitos: requirements.data.map((r) => ({
                idrequisito: r.idrequisito,
                cumplerequisito: data[`req_${r.idrequisito}`] === "true",
              })),
            });
            changed(
              result.prefiltroaprobado
                ? `Cita registrada: ${result.fase}.`
                : `Prefiltro no aprobado: ${result.motivos_exclusion.map((m: Row) => `${m.motivo} (${m.definitivo ? "exclusión definitiva" : "exclusión temporal"})`).join("; ")}`,
            );
          }}
        />
      </Panel>
    </>
  );
}

export function AccountPage({ changed }: { changed: () => void }) {
  return (
    <div className="hv-grid">
      <Panel title="Cambiar contraseña">
        <Form
          fields={[
            {
              name: "current_password",
              label: "Contraseña actual",
              type: "password",
            },
            {
              name: "new_password",
              label: "Nueva contraseña",
              type: "password",
            },
          ]}
          submit="Actualizar contraseña"
          onSubmit={async (data) => {
            await request("auth/cambiar-password/", data);
            changed();
          }}
        />
      </Panel>
      <Panel
        title="Solicitar perfil sanitario"
        subtitle="El administrador revisará tu cargo y matrícula antes de habilitar el perfil."
      >
        <Form
          fields={[
            { name: "codigo", label: "Perfil solicitado", options: roles },
            { name: "cargo", label: "Cargo profesional" },
            { name: "registroprofesional", label: "Matrícula profesional" },
          ]}
          submit="Enviar solicitud"
          onSubmit={async (data) => {
            await request("personal/solicitudes/", data);
            changed();
          }}
        />
      </Panel>
    </div>
  );
}
