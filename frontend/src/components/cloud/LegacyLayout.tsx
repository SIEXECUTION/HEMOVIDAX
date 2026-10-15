import React, { useEffect, useRef } from "react";
import {
  ShieldCheck,
  X,
  Heart,
  CalendarDays,
  Droplet,
  CreditCard,
  ArrowRight,
  KeyRound,
} from "lucide-react";
import { Navbar } from "../Navbar";
import { Session } from "../../services/cloudApi";
import { UserSession, RoleCode, StaffRole } from "../../types";
import { Row, useResource, ResourceNotice } from "./ui";

export function LegacyNavbar({
  session,
  tab,
  onSelect,
  onLogin,
  onRegister,
  onLogout,
  onSwitch,
}: {
  session: Session | null;
  tab: string;
  onSelect: (tab: string) => void;
  onLogin: () => void;
  onRegister: () => void;
  onLogout: () => void;
  onSwitch: (role: string) => void;
}) {
  const account = session?.account;
  const legacy: UserSession | null =
    session && account
      ? {
          role: session.role as RoleCode,
          activeRole: session.role as RoleCode,
          usuarioId: account.idUsuario,
          nombreCompleto: account.persona?.nombreCompleto || account.username,
          username: account.username,
          email: account.email,
          rolesDisponibles: account.roles.map((r) => ({
            ...r,
            codigo: r.codigo as RoleCode,
          })),
          staff: !["DONANTE", "POSIBLE_DONADOR", "RECEPTOR"].includes(
            session.role,
          )
            ? {
                id: String(account.idUsuario),
                rol: session.role as StaffRole,
                nombre: account.persona?.nombreCompleto || account.username,
                cargo:
                  account.roles.find((r) => r.codigo === session.role)
                    ?.nombre || "",
                ci: account.persona?.ci || "",
                email: account.email,
                turno: "",
                credencial: "",
              }
            : undefined,
        }
      : null;
  const mapped: Record<
    string,
    "inicio" | "citas" | "historial" | "mapa" | "carnet" | "autoevaluacion"
  > = {
    portal: "inicio",
    citas: "citas",
    historial: "historial",
    mapa: "mapa",
    carnet: "carnet",
  };
  return (
    <Navbar
      showDesktopNavigation={false}
      session={legacy}
      activeTab={mapped[tab] || "inicio"}
      onSelectTab={(value) =>
        onSelect(
          (
            { inicio: "portal", autoevaluacion: "citas" } as Record<
              string,
              string
            >
          )[value] || value,
        )
      }
      onOpenLogin={onLogin}
      onOpenRegister={onRegister}
      onLogout={onLogout}
      onOpenPrecheck={() => (session ? onSelect("citas") : onLogin())}
      onOpenChangePassword={() => onSelect("cuenta")}
      onSwitchRole={onSwitch}
      onOpenOtherRoles={() => onSelect("cuenta")}
    />
  );
}

export function LegacyModal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () =>
      Array.from(
        box.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]',
        ) || [],
      );
    focusable()[0]?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") close.current();
      if (event.key === "Tab") {
        const list = focusable(),
          first = list[0],
          last = list[list.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", keyboard);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/80 backdrop-blur-xs flex items-start justify-center p-3 sm:p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="bg-white rounded-3xl shadow-2xl max-w-2xl w-full border border-slate-200 overflow-hidden my-auto shrink-0"
      >
        <header className="bg-gradient-to-r from-rose-950 via-slate-900 to-rose-900 p-5 sm:p-6 text-white flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="w-11 h-11 rounded-2xl bg-rose-600/30 border border-rose-500/40 flex items-center justify-center">
              <ShieldCheck className="w-6 h-6 text-rose-300" />
            </span>
            <div>
              <h2 className="text-xl font-black font-['Outfit',sans-serif]">
                {title}
              </h2>
              <p className="text-xs text-rose-200 mt-1">
                Banco de Sangre & Transfusión HemoVida
              </p>
            </div>
          </div>
          <button
            aria-label="Cerrar ventana"
            onClick={onClose}
            className="p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full"
          >
            <X size={20} />
          </button>
        </header>
        <div className="hv legacy-forms legacy-dialog-body">{children}</div>
      </div>
    </div>
  );
}

export function LegacyRoleBanner({
  session,
  onAccount,
}: {
  session: Session;
  onAccount: () => void;
}) {
  const config: Record<string, [string, string, string]> = {
    ADMIN: [
      "from-slate-900 via-slate-800 to-rose-950",
      "Administración, Auditoría Forense & Control Institucional",
      "Gestiona cuentas, acreditaciones, umbrales de inventario e indicadores del banco de sangre.",
    ],
    DOC_TRIAJE: [
      "from-blue-950 via-slate-900 to-blue-950",
      "Evaluación Médica, Signos Vitales & Dictamen de Aptitud",
      "Consulta la admisión, registra el triaje y conserva el seguimiento de los diferimientos.",
    ],
    BIOQ_INTEGRAL: [
      "from-teal-950 via-slate-900 to-teal-950",
      "Control Serológico, Inmunohematología & Fraccionamiento",
      "Procesa las unidades en cuarentena, confirma resultados y asigna los componentes a sus ubicaciones.",
    ],
    PERS_COLECTA: [
      "from-slate-900 via-rose-950 to-slate-900",
      "Admisión, Asistencia Física, Viabilidad & Incentivos",
      "Verifica al donante, confirma la asistencia y registra la extracción, el consentimiento y el refrigerio.",
    ],
    TEC_LOGISTICA: [
      "from-red-950 via-slate-900 to-red-950",
      "Inventario, Trazabilidad & Logística Transfusional",
      "Consulta la disponibilidad, las reservas exclusivas y las unidades próximas a vencer.",
    ],
    MED_SOLICITANTE: [
      "from-blue-950 via-slate-900 to-blue-950",
      "Gestión Médica & Donación Autóloga",
      "Programa y consulta los protocolos de autodonación para cirugía.",
    ],
  };
  const [color, title, description] = config[session.role] || [
    "from-slate-900 to-rose-950",
    "Portal de Donación HemoVida",
    "Consulta tu carnet, tus citas y tu historial.",
  ];
  return (
    <section
      className={`bg-gradient-to-r ${color} rounded-3xl p-6 sm:p-8 text-white shadow-xl border border-slate-800/40 relative overflow-hidden`}
    >
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <span className="bg-white/10 border border-white/15 text-[11px] px-3 py-1 rounded-full font-bold">
              {
                session.account.roles.find((r) => r.codigo === session.role)
                  ?.nombre
              }
            </span>
            <span className="bg-white/10 text-white/90 text-[11px] px-3 py-1 rounded-full">
              {session.account.persona?.nombreCompleto ||
                session.account.username}
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl lg:text-4xl font-black font-['Outfit',sans-serif] tracking-tight">
            {title}
          </h1>
          <p className="text-sm text-slate-300 max-w-3xl leading-relaxed">
            {description}
          </p>
        </div>
        <button
          onClick={onAccount}
          className="px-4 py-3 bg-white/10 hover:bg-white/20 rounded-xl text-xs font-bold flex items-center gap-2 shrink-0"
        >
          <KeyRound size={16} />
          Mi cuenta y contraseña
        </button>
      </div>
    </section>
  );
}

export function LegacyDonorOverview({
  session,
  version,
  onSelect,
}: {
  session: Session;
  version: number;
  onSelect: (tab: string) => void;
}) {
  const resource = useResource<Row | null>(
      `donantes/carnet-digital/${session.account.persona?.idPersona}/`,
      null,
      version,
    ),
    c = resource.data;
  return (
    <>
      <div className="hv legacy-forms">
        <ResourceNotice {...resource} />
      </div>
      {c && (
        <>
          <section className="bg-gradient-to-br from-slate-900 via-slate-800 to-rose-950 text-white rounded-3xl p-6 sm:p-8 shadow-xl relative overflow-hidden border border-slate-700/40">
            <div className="absolute top-0 right-0 w-80 h-80 bg-rose-600/15 rounded-full blur-3xl pointer-events-none" />
            <div className="relative grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
              <div className="lg:col-span-7 space-y-4">
                <span className="inline-flex gap-2 items-center bg-white/10 border border-white/15 px-3 py-1 rounded-full text-xs font-semibold text-rose-200">
                  <Heart size={14} />
                  Portal de Donación HemoVida • Santa Cruz
                </span>
                <h1 className="text-3xl sm:text-4xl font-black font-['Outfit',sans-serif]">
                  ¡Hola, {session.account.persona?.nombres.split(" ")[0]}!
                </h1>
                <p className="text-sm text-slate-300">
                  C.I.: {c.ci} • Carnet:{" "}
                  <span className="font-mono text-rose-300">
                    {c.carnet_codigo}
                  </span>
                </p>
                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => onSelect("citas")}
                    className="px-5 py-3 rounded-xl bg-rose-600 hover:bg-rose-700 text-xs font-bold flex items-center gap-2"
                  >
                    <CalendarDays size={16} />
                    Agendar Donación
                    <ArrowRight size={15} />
                  </button>
                  <button
                    onClick={() => onSelect("carnet")}
                    className="px-5 py-3 rounded-xl bg-white/10 hover:bg-white/20 text-xs font-bold flex items-center gap-2"
                  >
                    <CreditCard size={16} />
                    Ver Carnet Digital
                  </button>
                </div>
              </div>
              <div className="lg:col-span-5 bg-white/10 border border-white/15 p-5 rounded-2xl space-y-3">
                <span
                  className={`text-xs font-bold ${c.elegibilidad.semaforo === "Rojo" ? "text-rose-300" : "text-amber-200"}`}
                >
                  {c.esPosibleDonador
                    ? "Postulante en evaluación"
                    : c.estado_habilitacion}
                </span>
                <h2 className="text-xl font-black font-['Outfit',sans-serif]">
                  {c.elegibilidad.dias_restantes > 0
                    ? `${c.elegibilidad.dias_restantes} días de recuperación`
                    : "Tu próxima evaluación"}
                </h2>
                <p className="text-xs text-slate-200 leading-relaxed">
                  {c.elegibilidad.motivo ||
                    "Completa el prefiltro y asiste a tu evaluación médica para confirmar la aptitud."}
                </p>
                <progress
                  aria-label="Recuperación biológica"
                  className="w-full h-2 accent-rose-500"
                  max="100"
                  value={c.elegibilidad.porcentaje_recuperacion}
                />
                <p className="text-[11px] text-slate-300">
                  Próxima fecha por descanso: {c.elegibilidad.proxima_fecha}
                </p>
              </div>
            </div>
          </section>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
            {[
              [Droplet, c.total_donaciones, "Donaciones registradas"],
              [Heart, `${c.volumen_total_aportado_ml} ml`, "Aporte histórico"],
              [ShieldCheck, c.grupo_sanguineo, "Grupo sanguíneo"],
              [
                CalendarDays,
                c.elegibilidad.proxima_fecha,
                "Próxima fecha por descanso",
              ],
            ].map(([Icon, value, label]) => {
              const Glyph = Icon as React.ElementType;
              return (
                <article
                  key={String(label)}
                  className="bg-white rounded-3xl border border-slate-200 shadow-xs p-6"
                >
                  <Glyph className="w-8 h-8 p-1.5 rounded-lg bg-rose-50 text-rose-600 mb-3" />
                  <strong className="block text-2xl font-black font-['Outfit',sans-serif] text-slate-900">
                    {String(value)}
                  </strong>
                  <span className="text-xs text-slate-500">
                    {String(label)}
                  </span>
                </article>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
