# Versionado de pesos del motor de readiness

## Por qué existe esto

No hay una fórmula pública de Garmin para el "Training Readiness" — los pesos que usa este proyecto (`DEFAULT_WEIGHTS` en `weights.py`) son una estimación propia v1, no algo derivado de un estándar externo. Van a necesitar ajuste una vez que haya suficiente historial real (recomendado: esperar los ~60 días que toma completar el baseline de HRV antes de recalibrar).

## Cómo funciona hoy (v1)

Todo el ajuste numérico del algoritmo vive en un solo lugar: `backend/app/readiness/weights.py`, en el objeto `DEFAULT_WEIGHTS`. Nada de esto es automático — el sistema no aprende de tus datos por sí solo (eso sería ML, explícitamente fuera de alcance del proyecto).

Los valores configurables son:

| Campo | Qué hace |
|---|---|
| `factor_weights` | Cuánto pesa cada factor (HRV, sueño, HR en reposo, estrés, body battery, carga de entrenamiento) en el score final. Suman 1.0. |
| `factor_polarity` | Si un valor más alto es mejor, más bajo es mejor, o si lo ideal es estar cerca de un valor objetivo (caso de la carga de entrenamiento/ACWR). |
| `z_to_points_slope` | Cuántos puntos (sobre 100) mueve una desviación estándar respecto a tu baseline personal. |
| `tie_threshold` | Qué tan cerca tienen que estar dos factores para considerarse "empatados" como causa dominante (hoy: 0.10 desviaciones estándar). |
| `insufficient_coverage_threshold` | Por debajo de qué % de factores disponibles el resultado pasa a "insuficiente" (hoy: 60%). |
| `calibrating_below_days` | Debajo de cuántos días de historial se muestra "calibrando" en vez de un número (hoy: 60 días, alineado con el spec — no hay rango parcial de 14-59 días). |
| `full_confidence_at_days` | A partir de cuántos días la confianza llega a 100% (hoy: 60 días). |
| `band_thresholds` | Los cortes de score que definen las bandas de recomendación: entrenar fuerte / moderado / suave / descansar (hoy: 80 / 60 / 40). |

## Cómo recalibrar (proceso manual)

1. **No edites `DEFAULT_WEIGHTS` in place.** Cada score guardado en la base queda etiquetado con el `weights_version` que lo generó (hoy: `"v1"`). Si sobrescribís los pesos sin cambiar la versión, los scores históricos pierden trazabilidad de qué fórmula los produjo.
2. Creá un nuevo objeto `ScoringWeights` con `version="v2"` (o el nombre que corresponda) y los valores ajustados.
3. Decidí cómo se selecciona la versión activa (hoy el código usa `DEFAULT_WEIGHTS` directo — si querés soportar múltiples versiones activas o comparar v1 vs v2 sobre el mismo historial, es un cambio de diseño en `engine.py`, no solo de datos).
4. Corré los tests existentes (`pytest backend/tests/unit/test_engine.py`) contra los nuevos pesos para confirmar que los casos "golden" (empates, datos faltantes, umbral de insuficiencia) siguen comportándose como esperás.
5. Guardá la razón del cambio en el commit — qué observaste que te hizo ajustar cada peso (ej: "HRV predecía mal mis días de descanso reales, bajé su peso de 0.30 a 0.20").

## Lo que NO hace el sistema (por ahora)

- No reentrena ni sugiere pesos nuevos automáticamente.
- No compara predicciones pasadas contra cómo te sentiste realmente (no hay input subjetivo capturado todavía).
- No corre múltiples versiones de pesos en paralelo para comparar resultados.

Si en algún momento querés cualquiera de esas tres cosas, es una funcionalidad nueva a planificar (probablemente empezando por capturar un input subjetivo diario — "¿cómo te sentiste hoy?" — antes de poder comparar nada).
