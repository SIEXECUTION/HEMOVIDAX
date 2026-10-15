import React, { useEffect, useState } from "react";
import { ArrowRight, ClipboardList } from "lucide-react";
import { request } from "../../services/cloudApi";
export type Row = Record<string, any>;
export type Option = { value: string | number; label: string };
export type Field = {
  name: string;
  label: string;
  type?: string;
  options?: Option[];
  required?: boolean;
  min?: number;
  max?: number;
  value?: string;
  help?: string;
};
export const roles: Option[] = [
  { value: "DOC_TRIAJE", label: "Médico de triaje" },
  { value: "PERS_COLECTA", label: "Recepción y colecta" },
  { value: "BIOQ_INTEGRAL", label: "Bioquímico integral" },
  { value: "TEC_LOGISTICA", label: "Logística" },
  { value: "MED_SOLICITANTE", label: "Médico solicitante" },
];
export const ages = ["Adulto", "Adolescente", "Pediátrico"].map((value) => ({
  value,
  label: value,
}));
export const options = (values: string[]) =>
  values.map((value) => ({ value, label: value }));
export const personFields: Field[] = [
  { name: "ci", label: "Documento de identidad" },
  { name: "nombres", label: "Nombres" },
  { name: "apellidos", label: "Apellidos" },
  {
    name: "sexo",
    label: "Sexo",
    options: ["M", "F", "O"].map((value, i) => ({
      value,
      label: ["Masculino", "Femenino", "Otro"][i],
    })),
  },
  { name: "fechaNacimiento", label: "Fecha de nacimiento", type: "date" },
  { name: "celular", label: "Celular", required: false },
  { name: "username", label: "Nombre de usuario" },
  { name: "email", label: "Correo electrónico", type: "email" },
  {
    name: "password",
    label: "Contraseña",
    type: "password",
    help: "Mínimo 8 caracteres, mayúscula, minúscula, número y símbolo.",
  },
];
export function useResource<T>(path: string, initial: T, version = 0) {
  const [data, setData] = useState<T>(initial),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    request<T>(path)
      .then((value) => {
        if (!cancelled) setData(value);
      })
      .catch((e) => {
        if (!cancelled) {
          setData(initial);
          setError(e.message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path, version]);
  return { data, error, loading };
}
export function ResourceNotice({
  error,
  loading,
}: {
  error: string;
  loading: boolean;
}) {
  return error ? (
    <p className="hv-error" role="alert">
      {error}
    </p>
  ) : loading ? (
    <p className="hv-muted" role="status">
      Cargando información…
    </p>
  ) : null;
}
export function Table({
  rows,
  columns,
  actions,
}: {
  rows: Row[];
  columns: [string, string][];
  actions?: (row: Row) => React.ReactNode;
}) {
  if (!rows.length)
    return (
      <div className="hv-empty">
        <ClipboardList size={26} />
        <p>No hay registros para mostrar.</p>
      </div>
    );
  return (
    <div className="hv-table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map(([key, label]) => (
              <th key={key}>{label}</th>
            ))}
            {actions && <th>Acciones</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.idcita || r.id || i}>
              {columns.map(([key]) => (
                <td key={key}>
                  {r[key] === null || r[key] === undefined
                    ? "—"
                    : typeof r[key] === "boolean"
                      ? r[key]
                        ? "Sí"
                        : "No"
                      : String(r[key])}
                </td>
              ))}
              {actions && (
                <td>
                  <div className="hv-actions">{actions(r)}</div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Panel({
  title,
  children,
  subtitle,
}: {
  title: string;
  children: React.ReactNode;
  subtitle?: string;
}) {
  return (
    <section className="hv-panel">
      <header>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </header>
      {children}
    </section>
  );
}
export function Form({
  fields,
  submit,
  onSubmit,
  children,
}: {
  fields: Field[];
  submit: string;
  onSubmit: (data: Row) => Promise<void>;
  children?: React.ReactNode;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <form
      className="hv-form"
      onSubmit={async (e) => {
        e.preventDefault();
        const form = e.currentTarget;
        const data: Row = Object.fromEntries(new FormData(form));
        fields.forEach((f) => {
          if (f.type === "checkbox") data[f.name] = data[f.name] === "on";
          if (f.type === "datetime-local" && data[f.name])
            data[f.name] = new Date(data[f.name]).toISOString();
        });
        setBusy(true);
        setError("");
        try {
          await onSubmit(data);
          form.reset();
        } catch (e) {
          setError(e instanceof Error ? e.message : "No se pudo guardar.");
        } finally {
          setBusy(false);
        }
      }}
    >
      <fieldset disabled={busy}>
        <div className="hv-fields">
          {fields.map((f) => (
            <label
              key={f.name}
              className={f.type === "checkbox" ? "hv-check" : ""}
            >
              {f.type !== "checkbox" && <span>{f.label}</span>}
              {f.options ? (
                <select
                  name={f.name}
                  required={f.required !== false}
                  defaultValue={f.value || ""}
                >
                  <option value="">Seleccionar</option>
                  {f.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  name={f.name}
                  type={f.type || "text"}
                  required={f.required !== false}
                  min={f.min}
                  max={f.max}
                  step={f.type === "number" ? "any" : undefined}
                  defaultValue={f.value}
                  autoComplete={
                    f.type === "password" ? "new-password" : undefined
                  }
                />
              )}
              {f.type === "checkbox" && <span>{f.label}</span>}
              {f.help && <small>{f.help}</small>}
            </label>
          ))}
        </div>
        {children}
        {error && (
          <p className="hv-error" role="alert">
            {error}
          </p>
        )}
        <button className="hv-primary" type="submit">
          {busy ? "Procesando…" : submit}
          <ArrowRight size={16} />
        </button>
      </fieldset>
    </form>
  );
}
