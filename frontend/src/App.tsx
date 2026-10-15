import React, { useEffect, useState } from "react";
import {
  Droplet,
  LogOut,
  RefreshCw,
  Heart,
  CalendarDays,
  CreditCard,
  MapPin,
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
import { LegacyLanding } from "./components/cloud/LegacyLanding";
import {
  LegacyNavbar,
  LegacyModal,
  LegacyRoleBanner,
  LegacyDonorOverview,
} from "./components/cloud/LegacyLayout";
import "./cloud.css";
import "./legacy.css";
const emptyOperations = {
  personas: [],
  triajes: [],
  extracciones: [],
  unidades: [],
  bolsas: [],
  autologas: [],
};
export default function App() {
  const [authOpen, setAuthOpen] = useState(false);
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
    setAuthOpen(false);
    setSession(s);
    setTab("portal");
    setError("");
    setMessage("");
  };
  useEffect(() => {
    const expired = () => {
      commit(null);
      setError("La sesión venció. Inicia sesión nuevamente.");
      setAuthOpen(true);
    };
    window.addEventListener("hemovida:expired", expired);
    return () => window.removeEventListener("hemovida:expired", expired);
  }, []);
  const changed = (msg = "Operación guardada correctamente.") => {
    setMessage(msg);
    setVersion((v) => v + 1);
  };
  const openAuth = (next: typeof mode) => {
    setMode(next);
    setError("");
    setMessage("");
    setAuthOpen(true);
  };
  if (!session)
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col font-['Plus_Jakarta_Sans',sans-serif] text-slate-800">
        <LegacyNavbar
          session={null}
          tab="portal"
          onSelect={() => openAuth("login")}
          onLogin={() => openAuth("login")}
          onRegister={() => openAuth("register")}
          onLogout={() => commit(null)}
          onSwitch={() => {}}
        />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
          <LegacyLanding
            onLogin={() => openAuth("login")}
            onRegister={() => openAuth("register")}
          />
        </main>
        <footer className="text-center border-t border-slate-200 py-6 text-xs text-slate-500">
          HemoVida · Banco de Sangre & Transfusión · Santa Cruz
        </footer>
        {authOpen && (
          <LegacyModal
            title="Acceso Seguro • Banco de Sangre HemoVida"
            onClose={() => {
              setAuthOpen(false);
              setPending(null);
            }}
          >
            <div className="hv-auth">
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
                        {
                          name: "email",
                          label: "Usuario o correo electrónico",
                        },
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
            </div>
          </LegacyModal>
        )}
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
    ...(!clinical
      ? ([
          ["historial", "Historial", ClipboardList],
          ["carnet", "Carnet Digital", CreditCard],
          ["mapa", "Centros", MapPin],
        ] as [string, string, React.ElementType][])
      : []),
    ["cuenta", "Mi cuenta", UserRound],
  ];
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-['Plus_Jakarta_Sans',sans-serif] text-slate-800">
      <LegacyNavbar
        session={session}
        tab={tab}
        onSelect={setTab}
        onLogin={() => {}}
        onRegister={() => {}}
        onLogout={() => commit(null)}
        onSwitch={(value) => commit({ ...session, role: value })}
      />
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 space-y-6">
        {clinical && (
          <LegacyRoleBanner
            session={session}
            onAccount={() => setTab("cuenta")}
          />
        )}
        <nav
          aria-label="Módulos de trabajo"
          className="legacy-tabs flex flex-wrap gap-2 bg-white rounded-2xl p-2 border border-slate-200 shadow-xs"
        >
          {navigation.map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`px-4 py-2.5 rounded-xl text-xs font-bold flex items-center gap-2 transition-colors ${tab === id ? "bg-slate-900 text-white shadow-md" : "text-slate-600 hover:bg-rose-50 hover:text-rose-700"}`}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
          <button
            className="ml-auto px-4 py-2 text-xs text-slate-500 flex items-center gap-2"
            disabled={catalog.loading || operations.loading}
            onClick={() => changed("Información actualizada.")}
          >
            <RefreshCw size={14} />
            Actualizar
          </button>
        </nav>
        {tab === "portal" && !clinical && session.account.persona && (
          <LegacyDonorOverview
            session={session}
            version={version}
            onSelect={setTab}
          />
        )}
        <div className={`hv legacy-forms legacy-role-${role}`}>
          {message && (
            <div className="hv-success" role="status">
              {message}
            </div>
          )}
          <ResourceNotice {...catalog} />
          {clinical && <ResourceNotice {...operations} />}
          {tab === "portal" && clinical && (
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
          {["historial", "carnet"].includes(tab) && session.account.persona && (
            <DonorCard
              personId={session.account.persona.idPersona}
              version={version}
              view={tab === "historial" ? "history" : "card"}
            />
          )}
          {tab === "mapa" && (
            <section className="hv-panel">
              <h2>Centros de la red hospitalaria</h2>
              <p className="hv-muted">
                Instituciones registradas en el banco de sangre.
              </p>
              {(catalog.data.instituciones || []).length === 0 ? (
                <p>No hay instituciones registradas.</p>
              ) : (
                (catalog.data.instituciones || []).map((i: Row) => (
                  <article
                    key={i.idinstitucion}
                    className="p-5 my-4 rounded-2xl border border-slate-200"
                  >
                    <h3>{i.nombreinstitucion}</h3>
                    <p>{i.direccion || "Dirección no registrada"}</p>
                    <p>{i.telefonocontacto || "Teléfono no registrado"}</p>
                    {i.direccion && (
                      <a
                        target="_blank"
                        rel="noopener noreferrer"
                        href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(i.direccion)}`}
                      >
                        Consultar dirección en el mapa
                      </a>
                    )}
                  </article>
                ))
              )}
            </section>
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
        </div>
      </main>
      <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500">
        HemoVida · Banco de Sangre & Transfusión · Santa Cruz
      </footer>
    </div>
  );
}
