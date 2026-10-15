import React, { useEffect, useState } from "react";
import {
  Droplet,
  LogOut,
  RefreshCw,
  Heart,
  CalendarDays,
  ShieldCheck,
  Activity,
  Package,
  FlaskConical,
  ClipboardList,
  UserRound,
  ArrowRight,
} from "lucide-react";
import {
  Session,
  readSession,
  saveSession,
  request,
} from "./services/cloudApi";
import {
  Row,
  Form,
  personFields,
  useResource,
  ResourceNotice,
} from "./components/cloud/ui";
import {
  DonorCard,
  Appointments,
  AccountPage,
} from "./components/cloud/DonorPages";
import { ClinicalPages } from "./components/cloud/ClinicalPages";
import {
  InventoryPage,
  AdminPage,
  AuditPage,
  KpiPage,
} from "./components/cloud/ManagementPages";
import "./cloud.css";
const emptyOperations = {
  personas: [],
  triajes: [],
  extracciones: [],
  unidades: [],
  bolsas: [],
  autologas: [],
};
export default function App() {
  const [session, setSession] = useState<Session | null>(readSession),
    [pending, setPending] = useState<Session | null>(null);
  const [mode, setMode] = useState<"login" | "register" | "reset" | "confirm">(
    "login",
  );
  const [tab, setTab] = useState("portal"),
    [version, setVersion] = useState(0),
    [message, setMessage] = useState(""),
    [error, setError] = useState("");
  const role = session?.role || "",
    clinical = [
      "ADMIN",
      "DOC_TRIAJE",
      "PERS_COLECTA",
      "BIOQ_INTEGRAL",
      "TEC_LOGISTICA",
      "MED_SOLICITANTE",
    ].includes(role);
  const commit = (s: Session | null) => {
    saveSession(s);
    setSession(s);
    setTab("portal");
    setError("");
    setMessage("");
  };
  useEffect(() => {
    const expired = () => {
      commit(null);
      setError("La sesión venció. Inicia sesión nuevamente.");
    };
    window.addEventListener("hemovida:expired", expired);
    return () => window.removeEventListener("hemovida:expired", expired);
  }, []);
  const changed = (msg = "Operación guardada correctamente.") => {
    setMessage(msg);
    setVersion((v) => v + 1);
  };
  if (!session)
    return (
      <div className="hv">
        <div className="hv-public">
          <div className="hv-intro">
            <a className="hv-brand" href="/">
              <Droplet fill="currentColor" />
              HemoVida
            </a>
            <div>
              <span className="hv-eyebrow">BANCO DE SANGRE</span>
              <h1>
                Conectamos tu
                <br />
                solidaridad
                <br />
                <em>con la vida.</em>
              </h1>
              <p>
                Un espacio para acompañar cada donación y cuidar cada etapa de
                su recorrido.
              </p>
              <div className="hv-intro-note">
                <Heart size={22} />
                <span>Tu próxima donación empieza aquí.</span>
              </div>
            </div>
            <small>
              Gestión de donantes · Seguridad transfusional · Trazabilidad
            </small>
          </div>
          <main className="hv-auth">
            <span className="hv-eyebrow">BIENVENIDO A HEMOVIDA</span>
            <h2>
              {pending
                ? "Selecciona tu perfil"
                : {
                    login: "Ingresa a tu cuenta",
                    register: "Crea tu cuenta de donante",
                    reset: "Recupera tu acceso",
                    confirm: "Crea una nueva contraseña",
                  }[mode]}
            </h2>
            <p className="hv-muted">
              {pending
                ? "Elige el perfil institucional con el que trabajarás."
                : "Tus datos y operaciones se consultan de forma segura."}
            </p>
            {error && (
              <p className="hv-error" role="alert">
                {error}
              </p>
            )}
            {message && (
              <p className="hv-success" role="status">
                {message}
              </p>
            )}
            {pending ? (
              <div className="hv-role-list">
                {pending.account.roles.map((r) => (
                  <button
                    key={r.codigo}
                    onClick={() => {
                      commit({ ...pending, role: r.codigo });
                      setPending(null);
                    }}
                  >
                    <UserRound size={20} />
                    {r.nombre}
                    <ArrowRight size={18} />
                  </button>
                ))}
                <button onClick={() => setPending(null)}>Volver</button>
              </div>
            ) : (
              <>
                {mode === "login" && (
                  <Form
                    fields={[
                      {
                        name: "username",
                        label: "Usuario o correo electrónico",
                      },
                      {
                        name: "password",
                        label: "Contraseña",
                        type: "password",
                      },
                    ]}
                    submit="Iniciar sesión"
                    onSubmit={async (data) => {
                      const result = await request(
                        "auth/login/",
                        data,
                        undefined,
                        true,
                      );
                      const value: Session = {
                        account: result.usuario,
                        access: result.tokens.access,
                        refresh: result.tokens.refresh,
                        role: "",
                      };
                      if (!value.account.roles.length)
                        throw new Error(
                          "La cuenta no tiene perfiles asignados. Contacta al administrador.",
                        );
                      if (value.account.roles.length > 1) setPending(value);
                      else
                        commit({
                          ...value,
                          role: value.account.roles[0].codigo,
                        });
                    }}
                  />
                )}
                {mode === "register" && (
                  <Form
                    fields={personFields}
                    submit="Registrarme"
                    onSubmit={async (data) => {
                      await request(
                        "auth/autoregistro/",
                        data,
                        undefined,
                        true,
                      );
                      setMessage("Cuenta creada. Ya puedes iniciar sesión.");
                      setMode("login");
                    }}
                  />
                )}
                {mode === "reset" && (
                  <Form
                    fields={[
                      { name: "email", label: "Usuario o correo electrónico" },
                    ]}
                    submit="Enviar código por correo"
                    onSubmit={async (data) => {
                      const result = await request(
                        "auth/recuperar-password/solicitar/",
                        data,
                        undefined,
                        true,
                      );
                      setMessage(result.message);
                      setMode("confirm");
                    }}
                  />
                )}
                {mode === "confirm" && (
                  <Form
                    fields={[
                      {
                        name: "token",
                        label: "Código recibido por correo",
                        help: "Pega el código completo. Es válido durante 15 minutos.",
                      },
                      {
                        name: "new_password",
                        label: "Nueva contraseña",
                        type: "password",
                      },
                    ]}
                    submit="Restablecer contraseña"
                    onSubmit={async (data) => {
                      await request(
                        "auth/recuperar-password/confirmar/",
                        data,
                        undefined,
                        true,
                      );
                      setMessage("Contraseña actualizada. Inicia sesión.");
                      setMode("login");
                    }}
                  />
                )}
                <div className="hv-auth-links">
                  <button
                    onClick={() => {
                      setMode(mode === "register" ? "login" : "register");
                      setMessage("");
                    }}
                  >
                    {mode === "register"
                      ? "Ya tengo una cuenta"
                      : "Crear cuenta de donante"}
                  </button>
                  <button
                    onClick={() => {
                      setMode(mode === "login" ? "reset" : "login");
                      setMessage("");
                    }}
                  >
                    {mode === "login"
                      ? "Olvidé mi contraseña"
                      : "Volver al inicio de sesión"}
                  </button>
                </div>
              </>
            )}
          </main>
        </div>
      </div>
    );
  return (
    <Workspace
      key={`${session.account.idUsuario}-${role}`}
      session={session}
      tab={tab}
      setTab={setTab}
      version={version}
      changed={changed}
      commit={commit}
      message={message}
      clinical={clinical}
    />
  );
}
function Workspace({
  session,
  tab,
  setTab,
  version,
  changed,
  commit,
  message,
  clinical,
}: {
  session: Session;
  tab: string;
  setTab: (v: string) => void;
  version: number;
  changed: (m?: string) => void;
  commit: (s: Session | null) => void;
  message: string;
  clinical: boolean;
}) {
  const role = session.role,
    admin = role === "ADMIN";
  const catalog = useResource<Row>(
    "inventario/catalogos/",
    { grupos: [], ubicaciones: [], componentes: [] },
    version,
  );
  const operations = useResource<Row>(
    clinical ? "inventario/operaciones/" : "inventario/catalogos/",
    emptyOperations,
    version,
  );
  const data = clinical ? operations.data : emptyOperations;
  const navigation: [string, string, React.ElementType][] = [
    ["portal", "Mi espacio", Heart],
    ["citas", "Citas y prefiltro", CalendarDays],
    ...(clinical
      ? ([
          ["admision", "Admisión", ClipboardList],
          ["clinica", "Atención clínica", Activity],
          ["inventario", "Inventario", Package],
          ["autologa", "Donación autóloga", ShieldCheck],
        ] as [string, string, React.ElementType][])
      : []),
    ...(["ADMIN", "BIOQ_INTEGRAL"].includes(role)
      ? ([["laboratorio", "Laboratorio", FlaskConical]] as [
          string,
          string,
          React.ElementType,
        ][])
      : []),
    ...(admin
      ? ([
          ["admin", "Administración", ShieldCheck],
          ["auditoria", "Auditoría", ClipboardList],
          ["indicadores", "Indicadores", Activity],
        ] as [string, string, React.ElementType][])
      : []),
    ["cuenta", "Mi cuenta", UserRound],
  ];
  return (
    <div className="hv hv-shell">
      <aside className="hv-sidebar">
        <a href="/" className="hv-brand">
          <Droplet fill="currentColor" />
          HemoVida
        </a>
        <span className="hv-eyebrow">BANCO DE SANGRE</span>
        <nav>
          {navigation.map(([id, label, Icon]) => (
            <button
              key={id}
              className={tab === id ? "active" : ""}
              onClick={() => setTab(id)}
            >
              <Icon size={18} />
              {label}
            </button>
          ))}
        </nav>
        <div className="hv-sidebar-bottom">
          <ShieldCheck size={18} />
          <span>
            Una donación.
            <br />
            Una nueva oportunidad.
          </span>
        </div>
      </aside>
      <div className="hv-workspace">
        <header className="hv-topbar">
          <span>Portal institucional</span>
          <div>
            <select
              aria-label="Perfil activo"
              value={role}
              onChange={(e) => commit({ ...session, role: e.target.value })}
            >
              {session.account.roles.map((r) => (
                <option key={r.codigo} value={r.codigo}>
                  {r.nombre}
                </option>
              ))}
            </select>
            <button onClick={() => commit(null)} title="Cerrar sesión">
              <LogOut size={18} />
            </button>
          </div>
        </header>
        <main className="hv-main">
          <div className="hv-page-title">
            <div>
              <span className="hv-eyebrow">
                HEMOVIDA / {navigation.find((n) => n[0] === tab)?.[1]}
              </span>
              <h1>
                {tab === "portal"
                  ? `Hola, ${session.account.persona?.nombres || session.account.username}`
                  : navigation.find((n) => n[0] === tab)?.[1]}
              </h1>
              <p className="hv-muted">
                {new Date().toLocaleDateString("es-BO", {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}
              </p>
            </div>
            <button
              className="hv-secondary"
              disabled={catalog.loading || operations.loading}
              onClick={() => changed("Información actualizada.")}
            >
              <RefreshCw size={16} />
              Actualizar
            </button>
          </div>
          {message && (
            <div className="hv-success" role="status">
              {message}
            </div>
          )}
          <ResourceNotice {...catalog} />
          {clinical && <ResourceNotice {...operations} />}
          {tab === "portal" && (
            <>
              <div className="hv-banner">
                <Heart size={34} />
                <div>
                  <span className="hv-eyebrow">CADA GOTA CUENTA</span>
                  <h2>
                    {clinical
                      ? "Cuidamos cada etapa de la donación."
                      : "Gracias por ser parte de esta red de vida."}
                  </h2>
                  <p>
                    {clinical
                      ? "Consulta citas, valida la atención y conserva la trazabilidad de cada unidad."
                      : "Consulta tu carnet, revisa tu historial y prepara tu próxima visita."}
                  </p>
                </div>
              </div>
              {!clinical && session.account.persona && (
                <DonorCard
                  personId={session.account.persona.idPersona}
                  version={version}
                />
              )}{" "}
              {clinical && (
                <div className="hv-stats">
                  <div>
                    <Package />
                    <strong>{data.bolsas.length}</strong>
                    <span>Unidades consultadas</span>
                  </div>
                  <div>
                    <Activity />
                    <strong>{data.extracciones.length}</strong>
                    <span>Extracciones consultadas</span>
                  </div>
                  <div>
                    <ShieldCheck />
                    <strong>
                      {
                        data.autologas.filter(
                          (a: Row) => a.estadocita === "Programada",
                        ).length
                      }
                    </strong>
                    <span>Cirugías programadas</span>
                  </div>
                </div>
              )}
            </>
          )}
          {tab === "citas" && (
            <Appointments
              session={session}
              clinical={clinical}
              people={data.personas}
              version={version}
              changed={changed}
            />
          )}
          {["admision", "clinica", "laboratorio", "autologa"].includes(tab) &&
            clinical && (
              <ClinicalPages
                tab={tab}
                role={role}
                catalog={catalog.data}
                operations={data}
                version={version}
                changed={changed}
              />
            )}
          {tab === "inventario" && clinical && (
            <InventoryPage operations={data} version={version} />
          )}
          {tab === "admin" && admin && (
            <AdminPage
              catalog={catalog.data}
              version={version}
              changed={changed}
            />
          )}
          {tab === "auditoria" && admin && <AuditPage />}
          {tab === "indicadores" && admin && <KpiPage version={version} />}
          {tab === "cuenta" && <AccountPage changed={changed} />}
          <footer className="hv-footer">
            HemoVida · Banco de Sangre
            <span>Cuidando la vida, en cada paso.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
