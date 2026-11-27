# Cómo contribuir

¡Gracias por ayudar! Este proyecto vive de la precisión: un número mal leído puede convertirse en una acusación injusta. Por eso estas reglas son estrictas.

## Preparar el entorno

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"
pytest
```

Las pruebas no necesitan red, así que el firewall de la UNA no las afecta.

## Reglas

1. **No subas `data/raw/`.** Los documentos originales se vuelven a descargar con `finanzas descargar`.
2. **Toda corrección del parser lleva una prueba con el caso real.** Agrega el caso a `scripts/crear_fixtures.py`, genera el fixture con `python scripts/crear_fixtures.py` y escribe la prueba en `tests/`. No edites a mano los JSON de `tests/fixtures/`: son filas reales.
3. **No cambies un umbral de señal sin actualizar `docs/metodologia.md`.**
4. **Lenguaje neutral.** En el código, la documentación y los issues se habla de «señales» e «inconsistencias», nunca de «fraude», «robo» o «corrupción».
5. **No intentes saltarte el firewall** ni las restricciones del servidor de la UNA. Respeta la pausa entre solicitudes.

## Ramas y commits

- Trabaja en una rama: `feat/...`, `fix/...`, `docs/...`.
- Antes de abrir un PR, corre `pytest` y `finanzas procesar`, y revisa si cambió `data/processed/`.
- Si tu cambio modifica los CSV procesados, explica en el PR por qué cambian las cifras.

## Reportar un error de datos

Abre un issue con:

- el informe (URL de `fuente_url`), la hoja y el código de cuenta;
- el valor que ves en el documento y el valor que da la herramienta.

## Conducta

Este proyecto sigue el [Código de conducta](CODE_OF_CONDUCT.md).
