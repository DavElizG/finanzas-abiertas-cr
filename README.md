# finanzas-abiertas-cr

Herramienta de código abierto para descargar, normalizar y visualizar los datos financieros públicos de instituciones costarricenses. Empieza por la **Universidad Nacional (UNA)**: presupuesto, modificaciones, ejecución mensual y señales para revisar.

> **Aviso.** Las *señales* y las *inconsistencias* que muestra esta herramienta son **preguntas para investigar, no acusaciones** ni prueba de irregularidades. Una diferencia puede venir del documento original o de un error de lectura de este código. Es un proyecto **independiente, sin afiliación con la UNA**. Cítalo si lo usas, pero no uses logos institucionales ni lo presentes como información oficial.

## Qué hace

1. **Descarga** los documentos del repositorio institucional [documentos.una.ac.cr](https://documentos.una.ac.cr) usando su API pública (DSpace 6, `/rest`). Va con pausas entre solicitudes, verifica el MD5 de cada archivo y deja un manifiesto con la URL de origen de cada uno.
2. **Lee** los informes de ejecución presupuestaria en Excel, aunque el formato cambia de un año a otro. Las columnas se reconocen por el texto del encabezado, no por su posición.
3. **Valida** que las cifras del documento cuadren consigo mismas: identidades contables, jerarquía de cuentas, total del documento y suma de programas.
4. **Marca señales** con reglas simples y públicas: sobregiros, gasto sin presupuesto, modificaciones grandes, subejecución y gasto concentrado en diciembre.
5. **Detecta cuentas atípicas** con un modelo exploratorio (Isolation Forest).
6. **Muestra todo** en un dashboard de Plotly Dash, con cinco pestañas:
   - **Resumen**: qué pasó en el año contado en frases simples, a dónde va cada ₡100, cómo evolucionó el presupuesto, qué tanto se ejecuta cada partida y cómo se reparte entre programas.
   - **Explorar el gasto**: un mapa por el que se baja de partida a grupo y a subpartida. Cada cuenta tiene una ficha con su historia, lo pagado mes a mes, sus modificaciones, sus señales y la hoja y fila exactas del Excel original.
   - **Cambios al presupuesto**: cada modificación interna y cada presupuesto extraordinario, y las cuentas que más dinero ganaron o perdieron.
   - **Señales para revisar**: tarjetas que explican cada tipo de señal y sirven de filtro; un clic en una fila abre la ficha de esa cuenta.
   - **Calidad de los datos**: las inconsistencias internas de cada documento.

## Fuentes y marco legal

- Constitución Política, **art. 30**: libre acceso a información de interés público.
- **Ley 10554**, Ley Marco de Acceso a la Información Pública (2024).
- **Ley 10240**, transparencia en el suministro de información del sector público.
- La Contraloría General de la República (CGR) fiscaliza los presupuestos de las universidades (Ley 8131).

Los documentos originales son información pública de la UNA y **no se relicencian**. Cada fila procesada conserva la URL del documento del que salió (`fuente_url`).

## Datos que cubre

Comunidad «Información Financiera» del Programa de Gestión Financiera:

Inventario verificado contra la API en noviembre de 2026:

| Serie (`--serie`) | Archivos | PDF | Excel | Estado |
|---|---|---|---|---|
| `ejecucion` | — | 2011–2026 | 2016–2025 | **Procesada** (23 informes en Excel) |
| `liquidacion` | 23 | 2011–2025 | 2016–2017, 2019–2023 | **Procesada** (7 en Excel) |
| `extraordinarios` | 52 | 2011–2026 | 2017–2025 | Solo descarga |
| `presupuesto_ordinario` | 41 | 2011–2026 | 2016–2023 | Solo descarga |
| `proyecto_presupuesto` | 24 | 2014–2026 | 2016–2020 | Solo descarga |
| `estados_mensuales` | 808 | 2014–2025 (ZIP 2024–2026) | 2017–2022 | Solo descarga |
| `estados_auditados` | 23 | 2014–2024 | — | Solo descarga |
| `auditoria_liquidacion` | 9 | 2016–2024 | — | Solo descarga |
| `activos_inmuebles` | 9 | 2018–2019 | 2018–2023 (ODS 2024) | Solo descarga |
| `alquileres` | 9 | — | 2016–2022 | Solo descarga |

La **liquidación presupuestaria** es el cierre oficial del año y trae las mismas tablas por programa al 31 de diciembre. Se usa para los años que no tienen informe de ejecución de diciembre en Excel (**2019**). Donde existen ambos documentos, se comparan cuenta por cuenta. **2018** sigue sin cierre en Excel: tanto su informe de diciembre como su liquidación solo están en PDF. El cierre de 2025 todavía no se ha publicado en Excel.

## Instalación y uso

Requiere Python 3.10 o superior.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   ·   macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest                                    # no necesita red

finanzas listar    --serie ejecucion --formatos xlsx
finanzas descargar --serie ejecucion   --formatos xlsx --desde 2016
finanzas descargar --serie liquidacion --formatos xlsx   # opcional: cierres oficiales
finanzas procesar
finanzas dashboard                        # http://127.0.0.1:8050
```

Archivos que se generan en `data/processed/una/` (sí se versionan):

| Archivo | Contenido |
|---|---|
| `ejecucion.csv` | Una fila por informe × programa × cuenta, con presupuesto inicial, variaciones, presupuesto total, girado mes a mes, compromisos, gastado y disponible, todo en colones. La columna `documento` dice si la fila sale de un informe de ejecución o de la liquidación |
| `liquidacion.csv` | Todas las filas de las liquidaciones, con el mismo formato |
| `modificaciones.csv` | Cada modificación interna y cada presupuesto extraordinario, por cuenta |
| `validacion.csv` | Inconsistencias internas del documento (o de la lectura) |
| `senales.csv` | Señales para revisar en subpartidas |
| `informes.csv` | Totales por informe y programa |
| `anomalias.csv` | Puntaje de anomalía por subpartida al cierre de año |

Los documentos descargados quedan en `data/raw/`, que **no se sube a git**. Se pueden volver a bajar con el manifiesto de `data/manifest/`.

## Metodología

La definición exacta de cada validación, señal y umbral está en [docs/metodologia.md](docs/metodologia.md).

## Limitaciones conocidas

- **Firewall de la UNA.** El repositorio bloquea muchas IP de servidores en la nube, así que la descarga debe correrse desde una conexión normal y no desde GitHub Actions. Si el servidor responde con HTML, el programa se detiene y avisa; no intenta saltarse el bloqueo. Ante cortes de conexión pasajeros reintenta tres veces, con esperas de 5, 20 y 60 segundos.
- **El formato cambia entre años.** Hay erratas («DICIEMRE»), fechas de encabezado guardadas como número de serie, hojas sin unidad declarada y títulos con la fecha equivocada. El parser maneja los casos que se conocen y deja constancia en `validacion.csv`.
- **Informes de 2016 a 2019 (formato resumen).** No traen el girado mes a mes.
- **Otras series.** Por ahora solo se procesan los informes de ejecución; las demás series se pueden descargar, pero todavía no se leen.
- **Un informe por corte.** Si hay dos documentos con la misma fecha de corte, se usa el más reciente y se anota.

## Hoja de ruta

- [x] Procesar las liquidaciones en Excel (2016–2023)
- [ ] Procesar los presupuestos extraordinarios (Excel 2017–2025)
- [ ] Leer el cierre de 2018 desde PDF
- [ ] Extraer los PDF (liquidaciones anteriores, estados financieros, auditorías)
- [ ] Comparar con UCR, UNED, UTN y TEC usando el clasificador por objeto del gasto
- [ ] Contratación pública (SICOP): concentración de proveedores y contratación directa
- [ ] Publicar el dashboard (Render o Hugging Face Spaces) leyendo los CSV versionados
- [ ] Migrar las tablas a `dash-ag-grid` (DataTable quedará obsoleto)

## Contribuir

Ver [CONTRIBUTING.md](CONTRIBUTING.md). Las correcciones de lectura siempre van con una prueba que use el caso real.

## Licencias y cómo citar

- **Código:** [MIT](LICENSE).
- **Datos procesados y documentación:** [CC BY 4.0](LICENSE-DATA).
- **Documentos originales:** información pública de la Universidad Nacional; consulta cada uno en su URL de origen.

Para citar el proyecto, usa el botón «Cite this repository» de GitHub, que sale de [CITATION.cff](CITATION.cff).
