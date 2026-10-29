/** Tipos y etiquetas del Liquidador de horas. */

export type Periodo = {
  /** quincena: 1 (días 1-15), 2 (16 a fin de mes) o 0 (mensual: el mes completo) */
  id: number; anio: number; mes: number; quincena: number; tipo: string; etiqueta: string; desde: string; hasta: string;
  /** Nombre de la nómina dentro del periodo (Cliente 1, Administrativa…); las anteriores quedaron como «General» */
  nombre: string;
  /** Nómina por horas: se pagan las horas trabajadas y el auxilio por día trabajado; descuenta salud y/o pensión según se marque */
  tipo_nomina?: "normal" | "horas"; descuenta_salud?: boolean; descuenta_pension?: boolean;
  estado: "borrador" | "calculada" | "cerrada"; archivo: string | null; advertencias: string[];
  cargado_en: string | null; calculado_en: string | null; cerrado_en: string | null; creado_en: string | null; empleados: number;
  /** Umbral semanal de horas: se marca al liquidar y vale para cada carga o recálculo del periodo */
  umbral_activo: boolean; umbral_horas: number; umbral_horas_novedad: number;
};

export type SemanaUmbral = { desde: string; hasta: string; dias_periodo: number; justificados: number; umbral: number; trabajadas: number;
  extras: number; pagadas: number; descontadas: number };

/** "Quincena 1", "Quincena 2" o "Mensual" */
export const nombrePeriodo = (p: Pick<Periodo, "quincena">) => (p.quincena === 0 ? "Mensual" : `Quincena ${p.quincena}`);

export type Resultado = {
  empleado_id: number; documento: string; nombre: string; cargo: string;
  horas: Record<string, number>; dias: Record<string, number>; total_horas: number;
  /** Solo con el permiso liquidador.nomina.ver */
  devengado?: number | null; neto?: number | null; nomina?: Nomina | null;
  /** Solo en el detalle, con el umbral semanal activo */
  umbral_semanas?: SemanaUmbral[];
  /** También está en otra nómina de fechas que se cruzan */
  otras_nominas?: boolean;
};

export type DescuentoAplicado = { id: number; tipo: TipoDescuento; descripcion: string; valor: number; calculo: string; observacion: string };

/** Nómina de una persona en el periodo (services/nomina.py). */
export type Nomina = {
  salario: number; salario_minimo: boolean; valor_dia: number; valor_hora: number; horas_mes: number;
  dias_salario: number; dias_incapacidad: number; incapacidad_empresa: number; incapacidad_eps: number; dias_auxilio: number; dias_sin_pago: number;
  basico: number; incapacidad: number; auxilio: number; horas: Record<string, number>; valores: Record<string, number>;
  recargos: number; extras: number; devengado: number; ibc: number; salud: number; salud_pct: number; pension: number; pension_pct: number;
  descuentos: DescuentoAplicado[]; prestamos: number; embargos: number; cuotas?: number; deducciones: number; neto: number; tarifas: string[];
  /** Auxilios no prestacionales: no son base de salud y pensión salvo lo que pase del 40 % (exceso_no_salarial) */
  auxilios?: { id: number | string; descripcion: string; valor: number; calculo: string }[]; auxilios_no_prestacionales?: number;
  dias_ausencia?: number; dias_tnl?: number; exceso_no_salarial?: number; alertas?: string[];
  vacaciones?: VacacionesNomina | null; vacaciones_valor?: number;
  /** Novedades manuales de esta nómina (mayor/menor valor pagado, horas pendientes…) */
  novedades?: NovedadAplicada[]; novedades_devengo?: number; novedades_deduccion?: number;
  /** Días con código 180 (incapacidad de más de 180 días): no se pagan; SERA provisiona la seguridad social */
  seguridad_social_180?: SeguridadSocial180 | null; provision_ss_180?: number;
  /** Nómina por horas */
  /** Licencias remuneradas (códigos marcados «Remunerado» en Turnos): salario ÷ 30 por día */
  licencias?: { codigo: string; nombre: string; dias: number; valor: number }[]; licencias_valor?: number; dias_licencia?: number;
  /** Marcado como pensionado en la ficha: no descuenta pensión */
  pensionado?: boolean;
  por_horas?: boolean; horas_pagadas?: number; dias_trabajados?: number; dias_auxilio_otra_nomina?: number;
};

export type SeguridadSocial180 = {
  dias: number; dias_base: number; base: number; exonerado: boolean; salud_empleado: number; pension_empleado: number;
  salud_empleador: number; pension_empleador: number; total: number;
  porcentajes: { salud_empleado: number; pension_empleado: number; salud_empleador: number; pension_empleador: number };
};

export type NovedadAplicada = {
  id: number; tipo: string; descripcion: string; valor: number; calculo: string; salarial: boolean; deduccion: boolean;
  nomina_origen: string | null; observacion: string;
};

/** Novedad manual registrada en una nómina (routes/novedades.py) */
export type Novedad = {
  id: number; empleado_id: number; documento: string; nombre: string; tipo: string; descripcion: string; horas: Record<string, number>;
  fecha_causacion: string | null; valor_escrito: number | null; salarial: boolean; nomina_origen: string | null; origen_registro: string;
  valor: number | null; calculo: string | null; deduccion: boolean | null; observacion: string;
};

export const TIPOS_NOVEDAD: [string, string, string][] = [
  ["auxilio_intermunicipal", "Auxilio intermunicipal", "Rodamiento por transporte intermunicipal: no prestacional, se paga solo en esta nómina y no hace base de salud y pensión"],
  ["auxilio_variable", "Auxilio no prestacional variable", "Otro auxilio no prestacional que se paga solo en esta nómina; no hace base de salud y pensión"],
  ["mayor_valor", "Mayor valor pagado", "Se descuenta: se pagó de más en una nómina anterior"],
  ["menor_valor", "Menor valor pagado", "Se paga: se pagó de menos en una nómina anterior (hace base de salud y pensión)"],
  ["horas_extras", "Horas extras pendientes", "Horas por concepto valoradas con la tarifa de la fecha en que se causaron"],
  ["recargos", "Recargos pendientes", "Horas por concepto valoradas con la tarifa de la fecha en que se causaron"],
  ["otro_devengo", "Otro devengo", "Se paga; marque si es salarial (hace base de salud y pensión)"],
  ["otra_deduccion", "Otra deducción", "Se descuenta del neto"],
];

export type SaldoVacaciones = {
  fecha_ingreso: string; corte: string; causados: number; previos: number; liquidador: number; pendientes: number;
  /** Fecha de corte del libro de vacaciones: «previos» son los disfrutados hasta ese día */
  corte_libro?: string | null;
};

/** Vacaciones liquidadas en el periodo: los días hábiles descuentan del saldo; los no hábiles también se pagan */
export type VacacionesNomina = {
  dias_habiles: number; dias_no_habiles: number; habiles_calendario: number; valor_habiles: number; valor_no_habiles: number; valor: number;
  salario: number; promedio: number; promedio_sugerido: number; meses_promedio: number; promedio_manual: boolean;
  base: number; valor_dia: number; dias_habiles_empleado: string; saldo: SaldoVacaciones | null;
};

export type VacacionPeriodo = VacacionesNomina & { empleado_id: number; documento: string; nombre: string; editable: boolean; alertas: string[] };

export const DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

export type TotalesNomina = Record<"basico" | "incapacidad" | "recargos" | "extras" | "auxilio" | "devengado" | "salud" | "pension" | "embargos" | "prestamos" | "cuotas" | "novedades_devengo" | "novedades_deduccion" | "deducciones" | "neto" | "provision_ss_180", number>;

export type Tarifa = {
  id: number; vigente_desde: string; smlmv: number; auxilio_transporte: number; horas_mes: number; salud_pct: number; pension_pct: number;
  porcentajes: Record<string, number>; nota: string; actualizado_en: string | null;
};

export type Descuento = {
  id: number; empleado_id: number; documento: string; nombre: string; tipo: TipoDescuento; descripcion: string;
  valor_mensual: number | null; porcentaje: number | null; monto_total: number | null; desde: string; hasta: string | null;
  quincena: Quincena; activo: boolean; descontado: number; saldo: number | null;
};

/** Préstamo, embargo o cuota (descuento periódico autorizado: plan exequial, pólizas, aportes…) */
export type TipoDescuento = "prestamo" | "embargo" | "cuota";
export const TIPOS_DESCUENTO: Record<TipoDescuento, [string, string]> = {
  prestamo: ["Préstamo", "bg-sky-100 text-sky-800"],
  embargo: ["Embargo", "bg-rose-100 text-rose-800"],
  cuota: ["Cuota", "bg-violet-100 text-violet-800"],
};

/** En qué quincena aplica un préstamo, embargo, cuota o auxilio: la mitad en cada una, o completo en una sola */
export type Quincena = "ambas" | "primera" | "segunda";
export const QUINCENAS: [Quincena, string][] = [["ambas", "Ambas quincenas"], ["primera", "Solo 1.ª quincena"], ["segunda", "Solo 2.ª quincena"]];

export type Auxilio = {
  id: number; empleado_id: number; documento: string; nombre: string; descripcion: string; valor_mensual: number;
  desde: string; hasta: string | null; quincena: Quincena; activo: boolean; pagado: number;
};

export type Dia = { fecha: string; codigo: string; turno: string; tipo_dia: string; clase: string; horas: Record<string, number> };

export type Turno = {
  id: number; codigo: string; nombre: string; hora_inicio: string; hora_fin: string; horas_ordinarias: number;
  horas_extras: number; remunerado: boolean; incapacidad: boolean; justifica_umbral: boolean; vacaciones: boolean; activo: boolean; clase: string;
};

export type Matriz = Record<string, Record<string, number>>;

export type Festivo = { fecha: string; descripcion: string; origen: "nacional" | "quitado" | "manual"; ajuste_id: number | null; vigente: boolean };

export type Empleado = {
  id: number; documento: string; nombre: string; cargo: string; quincenas: number; ultima: string | null; salario?: number | null;
  /** Días hábiles para vacaciones: 0 = lunes … 6 = domingo */
  dias_habiles: number[]; fecha_ingreso: string | null; vacaciones_previas: number; vacaciones_liquidador: number;
  saldo_vacaciones: SaldoVacaciones | null;
  /** Clase de riesgo ARL (1 a 5) */
  arl_clase: number | null;
  estado: "activo" | "retirado"; fecha_retiro: string | null; tipo_personal: "operativo" | "administrativo" | null; puesto: string | null;
};

/** Ficha del personal: solo con el permiso liquidador.personal.ver */
export type DatosPersonales = {
  tipo_personal: string | null; puesto: string | null; tipo_contrato: string | null; sexo: string | null; fecha_nacimiento: string | null;
  rh: string | null; pais_nacimiento: string | null; depto_nacimiento: string | null; ciudad_nacimiento: string | null;
  fecha_expedicion: string | null; pais_expedicion: string | null; depto_expedicion: string | null; ciudad_expedicion: string | null;
  estado_civil: number | null; extranjero: boolean; celular: string | null; correo: string | null; direccion: string | null;
  barrio: string | null; ciudad: string | null; eps: string | null; fondo_pensiones: string | null; pensionado: boolean;
  fondo_cesantias: string | null; caja_compensacion: string | null; plan_exequial: string | null; numero_cuenta: string | null;
  nivel_educativo: string | null; cursos: string | null; edad?: number; antiguedad_anios?: number;
};

export type Contrato = {
  id: number; fecha_inicio: string; fecha_retiro: string | null; tipo_contrato: string | null; cargo: string | null; puesto: string | null;
  motivo_retiro: string | null; observacion: string | null;
};

export type SalidaVacaciones = {
  id: number; tipo: "disfrutadas" | "compensadas"; desde: string | null; hasta: string | null; retorno: string | null;
  dias_habiles: number | null; estado: "historico" | "programada" | "cancelada"; observacion: string | null; origen: "libro" | "manual";
};

export type TramoVacaciones = { desde: string; hasta: string; dias: number; dias_habiles: number; antes_del_corte: boolean };

export type Hallazgo = { hoja: string; fila: number; documento: string | null; detalle: string };

export const CLASES_ARL: [number, string][] = [[1, "I"], [2, "II"], [3, "III"], [4, "IV"], [5, "V"]];

/** Los 12 conceptos, en el orden de las columnas del archivo de liquidación. */
export const CONCEPTOS: [string, string, string][] = [
  ["ordinary_day", "Diurnas ordinarias", "Diurnas ord."],
  ["ordinary_night", "Recargo nocturno", "Rec. noct."],
  ["holiday_day_surcharge", "Recargo festivo diurno", "Rec. fest. diur."],
  ["holiday_night_surcharge", "Recargo festivo nocturno", "Rec. fest. noct."],
  ["sunday_surcharge", "Recargo dominical diurno", "Rec. dom. diur."],
  ["sunday_night_surcharge", "Recargo dominical nocturno", "Rec. dom. noct."],
  ["overtime_day", "Extras ordinarias diurnas", "Ext. diur."],
  ["overtime_night", "Extras ordinarias nocturnas", "Ext. noct."],
  ["holiday_overtime_day", "Extras festivas diurnas", "Ext. fest. diur."],
  ["holiday_overtime_night", "Extras festivas nocturnas", "Ext. fest. noct."],
  ["sunday_overtime_day", "Extras dominicales diurnas", "Ext. dom. diur."],
  ["sunday_overtime_night", "Extras dominicales nocturnas", "Ext. dom. noct."],
];

/** Las 8 columnas de la matriz de un turno. */
export const TIPOS_DIA: [string, string][] = [
  ["weekday", "Ordinario"], ["saturday", "Sábado"], ["saturday_holiday", "Sáb. festivo"], ["sunday", "Domingo"],
  ["sunday_holiday_eve", "Dom. ant. fest."], ["holiday", "Festivo"], ["holiday_eve", "Ant. festivo"], ["holiday_double", "Fest. ant. fest."],
];

/** Clase de día: [clave, total, color, encabezado corto, un día] */
export const CLASES: [string, string, string, string, string][] = [
  ["trabajado", "Días trabajados", "bg-marca-50 text-marca-700", "Trab.", "Trabajado"],
  ["descanso_pago", "Descansos pagos", "bg-emerald-50 text-emerald-700", "Desc. pago", "Descanso pago"],
  ["libre", "Libres", "bg-slate-100 text-slate-700", "Libres", "Libre"],
  ["ausencia", "Ausencias", "bg-red-50 text-red-700", "Aus.", "Ausencia"],
  ["incapacidad", "Incapacidades", "bg-amber-50 text-amber-800", "Incap.", "Incapacidad"],
  ["novedad", "Días con novedad", "bg-violet-50 text-violet-700", "Novedad", "Novedad"],
];

export const ESTADO_PERIODO: Record<string, [string, string]> = {
  borrador: ["Sin cargar", "bg-amber-100 text-amber-800"],
  calculada: ["Calculada", "bg-green-100 text-green-800"],
  cerrada: ["Cerrada", "bg-slate-200 text-slate-700"],
};

export function horas(v: number | undefined): string {
  if (!v) return "–";
  return v.toLocaleString("es-CO", { maximumFractionDigits: 2 });
}

/** Conceptos que se pagan aparte del salario (las diurnas ordinarias ya están en el salario). */
export const CONCEPTOS_PAGO = CONCEPTOS.filter(([k]) => k !== "ordinary_day");

/** Recargos (se paga solo el adicional) y extras (la hora completa). */
export const RECARGOS = ["ordinary_night", "holiday_day_surcharge", "holiday_night_surcharge", "sunday_surcharge", "sunday_night_surcharge"];

/** Pagado por mes: suma de las nóminas cerradas del mes */
export const CAMPOS_PAGADO: [string, string][] = [
  ["basico", "Sueldo básico"], ["incapacidad", "Incapacidad"], ["vacaciones_valor", "Vacaciones"], ["licencias_valor", "Licencias remuneradas"], ["recargos", "Recargos"],
  ["extras", "Horas extras"], ["auxilios_no_prestacionales", "Auxilios no prestacionales"], ["auxilio", "Auxilio de transporte"],
  ["novedades_devengo", "Novedades (devengo)"], ["devengado", "Total devengado"], ["salud", "Salud"], ["pension", "Pensión"], ["embargos", "Embargos"], ["prestamos", "Préstamos"],
  ["cuotas", "Cuotas"], ["novedades_deduccion", "Novedades (deducción)"],
  ["deducciones", "Total deducciones"], ["neto", "Neto pagado"], ["provision_ss_180", "Provisión seg. social (cód. 180)"],
];

export type NominaDelMes = {
  id: number; nombre: string; tipo: string; etiqueta: string; estado: string; cerrado_en: string | null; personas: number; incluida: boolean;
} & Record<string, number | string | boolean | null>;

export type PersonaPagada = { empleado_id: number; documento: string; nombre: string; nominas: string[] } & Record<string, number | string | string[]>;

/** Costeo de nómina: costo empresa de un Excel de turnos, sin que cuente como pagado */
export type CostoEmpresa = {
  exonerado: boolean; arl_clase: number; arl_tarifa: number; base_aportes: number; base_arl: number; base_prestaciones: number; base_vacaciones: number;
  aportes: Record<string, number>; prestaciones: Record<string, number>; total_aportes: number; total_prestaciones: number;
  devengado: number; costo_total: number;
};

export type ParametrosCosteo = {
  exonerado: boolean; arl_clase: number; arl_tarifas: Record<string, number>;
  [k: string]: number | boolean | Record<string, number>;
};

/** Valor numérico de un % de los parámetros del costeo */
export const pct = (p: ParametrosCosteo, k: string) => Number(p[k] ?? 0);

export type CosteoResumen = {
  id: number; nombre: string; anio: number; mes: number; quincena: number; etiqueta: string; desde: string; hasta: string;
  archivo: string | null; personas: number; no_registradas: number; devengado: number; costo_total: number;
  creado_en: string | null; actualizado_en: string | null;
};

export type CosteoPersona = {
  documento: string; nombre: string; cargo: string; existe: boolean; dias: Record<string, number>; horas: Record<string, number>;
  /** Clase ARL de la columna "arl" del Excel o la del empleado; null = se usó la clase por defecto del costeo */
  arl_clase: number | null; arl_origen?: "excel" | "empleado" | null; auxilio_mensual: number;
  total_horas: number; nomina: Nomina; costo: CostoEmpresa;
};

export type Costeo = CosteoResumen & {
  umbral_activo: boolean; umbral_horas: number; umbral_horas_novedad: number; auxilio_mensual: number;
  parametros: ParametrosCosteo; advertencias: string[];
  totales: {
    personas: number; no_registradas: number; sin_arl: number; devengado: number; neto: number; total_aportes: number; total_prestaciones: number;
    costo_total: number; aportes: Record<string, number>; prestaciones: Record<string, number>;
  };
  resultados: CosteoPersona[];
};

export type ParametrosDefecto = { valores: ParametrosCosteo; nombres: Record<string, string>; aportes: string[]; prestaciones: string[] };
