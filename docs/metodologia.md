# Metodología

Este documento define cada paso del procesamiento para que cualquiera pueda reproducirlo o cuestionarlo. Todas las cifras se expresan en **colones corrientes**.

## 1. Fuente

Informes de ejecución presupuestaria en Excel publicados por el Programa de Gestión Financiera de la UNA en `documentos.una.ac.cr` (comunidad 375, una colección por año). Cada archivo se descarga por la API REST de DSpace y se verifica con el MD5 que publica el servidor.

### Liquidación presupuestaria

La liquidación es el cierre oficial del año y trae las mismas tablas por programa al 31 de diciembre, así que se lee con el mismo parser. Reglas para combinarla:

1. **El informe de ejecución de diciembre manda.** Si existe, sus cifras son las que se usan.
2. **La liquidación llena los huecos.** Si un año no tiene informe de diciembre en Excel (2019), sus filas entran a `ejecucion.csv` con `documento = liquidación`, y de ellas también se calculan señales, validaciones y anomalías.
3. **Donde hay ambos, se comparan** cuenta por cuenta (regla `liquidacion_vs_ejecucion`).
4. Todas las filas de la liquidación quedan además en `liquidacion.csv`.

Algunas liquidaciones (2016 y 2017) traen dos hojas por programa: la de «conformación», con el gasto en 0, y la de «ejecución». Se elige la hoja que trae gasto y, si ambas lo traen, la que tiene más cuentas.

## 2. Lectura de los informes

Cada libro trae una hoja por programa: **integrado** (toda la universidad), **académico**, **administrativo** y **vida universitaria**.

- **Hojas de ejecución.** Se toman las que tienen un encabezado «PRES. INICIAL» y códigos de cuenta con la forma `P GG SS`.
- **Programa.** Sale del título. Primero se buscan los programas específicos y después «INTEGRADO»/«CONSOLIDADO», porque muchos títulos dicen «CONSOLIDADO DE EGRESOS POR PROGRAMA / PROGRAMA ACADÉMICO».
- **Fecha de corte.** Sale de «AL dd DE mes DE aaaa». El mes se reconoce por sus tres primeras letras, para tolerar erratas como «DICIEMRE». La fecha del libro es la que más se repite entre sus hojas; si una hoja trae otra, se anota en `validacion.csv`.
- **Unidad.** «(Cifras en miles de colones)» multiplica por 1000. Si la hoja no la declara, se usa la unidad más común del mismo libro y se anota.
- **Columnas.** Se identifican por el texto combinado de la fila anterior, el encabezado y el subencabezado. En el formato resumen el encabezado «PARTIDA» cubre el código y el nombre; ese corrimiento se calcula a partir de la posición del nombre de la cuenta.
- **Solo la primera tabla.** Las hojas recientes repiten la tabla en miles; se lee solo hasta «TOTAL EGRESOS».
- **Girado mensual.** Solo se usan las columnas «GIRADO» de un mes. Las de «GIRADO ACUMULADO», «SEMESTRAL», «TRIMESTRAL» y «GIRADO AL dd-mm-aa» son saldos a una fecha y se ignoran. Si el informe no trae girado mensual, `girado = total gastado − compromisos`.
- **Celdas con error.** Valores como `#REF!` quedan como vacíos (NaN) y se registran.

### Niveles de cuenta

| Código | Nivel | Ejemplo |
|---|---|---|
| `0.00.00` | partida | Remuneraciones |
| `0.01.00` | grupo | Remuneraciones básicas |
| `0.01.01` | subpartida | Sueldos para cargos fijos |

Partidas del clasificador por objeto del gasto: 0 Remuneraciones · 1 Servicios · 2 Materiales y suministros · 3 Intereses y comisiones · 4 Activos financieros · 5 Bienes duraderos · 6 Transferencias corrientes · 7 Transferencias de capital · 8 Amortización · 9 Cuentas especiales.

## 3. Validaciones (`validacion.csv`)

Comparan dos cifras que **el propio documento** dice que deberían coincidir. La tolerancia es el mayor entre ₡1 000 y 0,0001 % del monto, para absorber el redondeo de Excel.

| Regla | Qué compara |
|---|---|
| `identidad_presupuesto` | inicial + recortes + variaciones = presupuesto total |
| `suma_modificaciones` | suma de las modificaciones internas = su total |
| `suma_extraordinarios` | suma de los presupuestos extraordinarios = su total |
| `suma_variaciones` | modificaciones + extraordinarios = total de variaciones |
| `identidad_gasto` | girado (suma de los meses) + compromisos = total gastado |
| `identidad_disponible` | presupuesto total − total gastado = disponible |
| `jerarquia` | las subcuentas suman a la cuenta padre (presupuesto inicial, total y gastado) |
| `total_documento` | las partidas suman a la fila «TOTAL EGRESOS» |
| `suma_programas` | académico + administrativo + vida universitaria = integrado, cuenta por cuenta |
| `liquidacion_vs_ejecucion` | la liquidación y el informe de diciembre del mismo año coinciden en presupuesto inicial, presupuesto total y gastado, cuenta por cuenta; también se reporta una cuenta que aparece en un solo documento |
| `error_celda` | celda con un error de Excel (`#REF!`, `#DIV/0!`…) |
| `metadatos` | fecha de corte, unidad o nombre del archivo inconsistentes |

Una fila en `validacion.csv` **no** dice quién se equivocó. Antes de atribuírsela al documento hay que revisar la hoja original y descartar un error del parser.

## 4. Señales (`senales.csv`)

Se calculan solo en **subpartidas**, para no contar el mismo monto dos veces. «Variaciones» incluye recortes, modificaciones internas y presupuestos extraordinarios.

| Señal | Condición | Umbral mínimo |
|---|---|---|
| `gasto_sin_presupuesto` | presupuesto total ≤ 0 y gastado > 0 | gastado ≥ ₡1 M |
| `sobregiro` | gastado > presupuesto total | diferencia ≥ ₡100 000 |
| `modificacion_alta` | \|variaciones\| > 50 % del presupuesto inicial | inicial ≥ ₡10 M |
| `creada_por_modificacion` | inicial ≤ 0 y variaciones > 0 | variaciones ≥ ₡10 M |
| `subejecucion` | gastado / total < 50 %, **solo en informes de diciembre** | total ≥ ₡50 M |
| `concentracion_diciembre` | girado en diciembre / girado del año > 30 % | girado ≥ ₡50 M |

Los umbrales están en `src/finanzas_cr/senales.py` (`UMBRALES`).

## 5. Cuentas atípicas (`anomalias.csv`)

Modelo **Isolation Forest** (scikit-learn, 300 árboles, `contamination=0.03`, semilla 42) aplicado a las subpartidas de los informes de diciembre, sin el integrado y con un presupuesto total de al menos ₡10 M. Usa cinco rasgos:

- ejecución: gastado / presupuesto total;
- variación relativa: variaciones / presupuesto inicial;
- peso de diciembre: girado en diciembre / girado del año;
- escala: log₁₀ del presupuesto total;
- cambio interanual: log₁₀ del presupuesto total frente al año anterior.

El puntaje indica qué tan **distinta** es una cuenta del resto, no si algo está mal. Es una herramienta para decidir qué revisar primero.

## 6. Hallazgos de la primera corrida (noviembre 2026)

Son ejemplos de lo que el sistema detecta en los documentos. Todos son preguntas abiertas:

- **Junio 2025, cuenta 4.02.06 «Adquisición de valores».** Los meses suman ₡22 487 M girados, pero la celda «TOTAL GASTADO» vale 0 y «DISPONIBLE» repite el presupuesto completo. El TOTAL EGRESOS del documento sí incluye ese monto, así que la suma de partidas (₡61 201 M) no coincide con el total (₡83 689 M).
- **Junio 2024, «Dietas».** Una celda del girado de mayo tiene `#REF!`.
- **Diciembre 2024.** El ítem dice «diciembre 2024», pero los archivos se llaman «dic 2025»; el contenido corresponde a 2024.
- **Junio 2019.** Las hojas de académico y vida universitaria traen el título «AL 31 DE MARZO DE 2019».
- **Marzo 2018.** La hoja académica tiene vacía la columna de presupuesto inicial, y la consolidada no trae la columna de modificaciones aunque el total sí las incluye.
- **Diciembre 2021, liquidación frente a informe.** En el programa académico, ₡306 M que el informe de diciembre registraba en «Recargo de funciones» aparecen en la liquidación como «Tiempo extraordinario». El total no cambia; cambia la cuenta. La comparación de los dos documentos encontró 23 diferencias en cuatro años (2016, 2020, 2021 y 2022).
- **Junio 2021.** En los programas, las columnas mensuales de girado tienen saldos acumulados de enero a marzo y vienen vacías de abril a junio.
