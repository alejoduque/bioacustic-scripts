# Protocolo de calibración en campo

[English](CALIBRATION.md) · **Español** · [← README](../README.es.md)

Todo lo que hay en este conjunto de herramientas se ha verificado hasta ahora con **audio sintético**, escrito para ejercitar rutas de código específicas. Eso demuestra que el pipeline hace mecánicamente lo que dice hacer. No dice nada sobre si los umbrales ecológicos son correctos para un sitio real.

Este documento es el plan para cerrar esa brecha cuando estén disponibles las grabaciones del bosque seco tropical. Está escrito para ser reproducible y citable: cada paso indica qué se mide, qué se decide a partir de ello y qué falsaría la decisión.

Hay dos asuntos abiertos. Todo lo demás se deriva de ellos.

---

## Asunto 1 — La frecuencia de muestreo debe decidirse antes del despliegue

**La decisión.** A qué frecuencia de muestreo desplegar los AudioMoth, por sitio y por temporada.

**Por qué no puede aplazarse.** Muestrear a una frecuencia *fs* representa frecuencias solo hasta Nyquist = *fs*/2. Por encima de ese límite la energía no desaparece: hace **aliasing**, se pliega a `|fs − f|` y aparece en una frecuencia que nunca estuvo presente. Nada aguas abajo puede detectar que esto ocurrió, y ningún reprocesamiento lo revierte. Una tarjeta grabada a la frecuencia equivocada carece permanentemente de la banda que no se eligió.

Esto no es teórico. Al construir el corpus de prueba se escribió un emisor sintético de 105 kHz en un archivo de 192 kHz; apareció en 87 kHz y fue clasificado a partir de esa frecuencia fantasma, sin ninguna advertencia en el pipeline.

| Frecuencia | Nyquist | Alcanza | No alcanza | Costo |
|---|---|---|---|---|
| 48 kHz | 24 kHz | aves, anuros, ortópteros | prácticamente toda la ecolocación | 1× |
| 96 kHz | 48 kHz | + Molossidae, algunos Vespertilionidae | Phyllostomidae de alta frecuencia | 2× |
| 192 kHz | 96 kHz | + casi toda la ecolocación neotropical | las especies CF más agudas | 4× |
| 256 / 384 kHz | 128 / 192 kHz | todo lo esperable en el Neotrópico | — | 5–8× |

El costo es almacenamiento, batería y tiempo de análisis a la vez: un despliegue a 192 kHz llena la tarjeta cuatro veces más rápido y acorta la batería en proporción.

**Protocolo.**

1. **Pilotear antes de comprometerse.** Desplegar al menos una unidad a 192 kHz durante una noche completa en cada tipo de cobertura, junto a las unidades de 48 kHz.
2. **Medir ocupación, no presencia.** Correr `--ultrasonic` sobre el piloto y leer las energías por banda en `events.json`. La pregunta no es "¿hay murciélagos?" (los hay), sino *qué bandas llevan energía*, y con qué frecuencia.
3. **Decidir por cobertura.** Si `ultrasonic_high` (80–160 kHz) está consistentemente vacía, 192 kHz es suficiente y 96 kHz podría serlo. Si está ocupada, 192 kHz es el piso.
4. **Registrar la decisión y su evidencia** en los metadatos del despliegue, para que quien lea después pueda distinguir una especie ausente de una especie irrepresentable.

**Qué la falsaría.** Energía acumulada contra el borde superior del gráfico sin estructura por debajo: es firma de aliasing, no de un emisor de alta frecuencia. Si aparece, volver a grabar el mismo sitio una frecuencia más arriba y comparar; el contenido genuino se desplaza a su frecuencia real, un alias se desplaza a otra parte.

**Higiene de despliegue que no cuesta nada y no se puede corregir después:**

- **Configurar el reloj y la zona horaria.** Toda regla diel (coro del amanecer, nocturno, crepuscular) depende de la marca temporal del AudioMoth. Una zona horaria equivocada reetiqueta en silencio un coro del amanecer como nocturno, y el error es invisible en la salida.
- **Cubrir el amanecer todos los días.** El inicio del coro se define como el primer evento biofónico entre las 03:00 y las 08:00. Un ciclo de trabajo que se salte una mañana produce un "retraso" espurio, indistinguible de un cambio fenológico real.
- **Mantener la convención de directorios.** La cobertura y la época se extraen de la ruta (`Época lluvias/Bosque de galería y-o ripario/`). Es el único lugar por donde esa información entra al análisis.

---

## Asunto 2 — Los umbrales del clasificador están sin calibrar

**La decisión.** Los umbrales numéricos al inicio de `bioacoustic_detector/classifier.py` que traducen rasgos medidos en roles ecológicos.

**La evidencia de que requieren trabajo.** En el corpus sintético de 45 eventos, cinco de los dieciséis roles se emitieron **cero veces**: `rain_event`, `wind_event`, `water_flow`, `mechanical_intrusion` y `aircraft_passage`. El contenido geofónico estaba presente, correctamente medido y claramente visible en los espectrogramas: simplemente nunca satisfizo las reglas.

Dos propiedades de los rasgos lo explican, y ambas importan para diseñar la corrección:

- **La planitud espectral se calcula sobre todo el espectro.** Una señal perfectamente ruidosa *dentro de su propia banda* obtiene un valor bajo si ocupa solo una parte del rango. La lluvia de banda limitada (60–1900 Hz) midió **0.21 y 0.29** frente a un umbral de **0.30**. La medida responde a "¿es ruidosa esta grabación?", no a "¿es ruidoso este evento?".
- **El centroide espectral se pondera por magnitud sobre todo el espectro**, de modo que un piso de ruido amplio y de bajo nivel lo arrastra hacia arriba. Esos mismos eventos de lluvia reportaron centroides de **6.5 y 7.7 kHz** pese a no tener energía alguna por encima de 2 kHz, razón por la cual la regla de antrofonía (`centroid < 1500`) tampoco los capturó.

Ninguno de los dos es un error aritmético. Ambos son el comportamiento documentado de descriptores espectrales globales aplicados a eventos de banda limitada.

**Dos correcciones candidatas, a decidir con los datos y no de antemano:**

- **(a) Reajustar los umbrales.** Lo más barato, sin cambios de código más allá de las constantes. Riesgo: ajustar al piso de ruido de un solo sitio.
- **(b) Calcular planitud y centroide *dentro de la banda dominante* como rasgos adicionales**, conservando los globales por comparabilidad con la literatura de índices publicada. Más fiel a lo que las reglas intentan expresar y con mayor probabilidad de transferir entre sitios. Cuesta algo de código y no invalida nada ya registrado, porque agrega campos en lugar de cambiar los existentes.

La opción (b) es la más defendible para una tesis; la (a) es el primer movimiento correcto para ver hasta dónde llega.

**Protocolo.**

1. **Sobre-segmentar deliberadamente.** Correr con `--sensitivity subtle`. Un evento perdido no se recupera anotando; un falso positivo se descarta en segundos.

   ```bash
   ./detect_events.sh <grabaciones>/ -o ./calib --sensitivity subtle --phenology
   ```

2. **Anotar en el orden de la galería.** `gallery.html` agrupa los clips por rol propuesto, de modo que quien anota confirma o rechaza una sola hipótesis a la vez: mucho más rápido que etiquetar desde cero, y hace visibles los desacuerdos entre anotadores como conglomerados.
3. **Registrar la etiqueta humana junto a la de la máquina**, nunca en su lugar. El par (propuesta, verificada) es la medición; la propuesta sola no lo es.
4. **Apuntar a un mínimo de ~50 eventos verificados por rol** que se pretenda usar, y ser explícito con los roles que no lo alcancen. Algunos no lo harán, y eso es un hallazgo, no una falla.
5. **Ajustar los umbrales al conjunto verificado** y volver a correr la detección: barato, frente a volver a anotar.
6. **Reportar precisión y exhaustividad por rol**, no exactitud global. Con este desbalance de clases (11 de 45 eventos correspondieron a un solo rol en el corpus de prueba), la exactitud global carece casi de sentido.
7. **Reservar la serie fenológica como validación.** Una calibración que no reproduce una transición seca–lluvias conocida en el sitio ajustó ruido.

**Qué falsaría una calibración.** Umbrales que separan roles limpiamente en una cobertura y colapsan en otra indican que lo equivocado es el rasgo y no el umbral, lo cual es la señal para pasar a la opción (b).

---

## Reglas de interpretación vigentes hasta completar la calibración

No son salvedades provisionales para olvidar: son la forma en que debe leerse la salida actual en cualquier análisis o publicación.

| Campo | Estado | Usar como |
|---|---|---|
| `onset_s`, `offset_s`, `duration_s` | medido | segmentación, ±1 marco |
| `band_energies`, `peak_flux` | medido | rasgos, directamente comparables |
| `dominant_band` | medido (argmax) | **la categoría confiable** |
| `aci`, `bio`, `ndsi`, `adi`, `aei` | medido, definiciones publicadas | rasgos, comparables entre estudios |
| `domain` | inferido, 4 clases | etiqueta débil defendible |
| `role` | **inferido, sin calibrar** | una hipótesis por verificar |
| `confidence` | **constante asignada a mano** | jerarquía de especificidad de la regla, no una probabilidad |

`confidence` en particular no se aprende ni se estima: cada rama de regla devuelve un número fijo elegido por el autor. Ordena las reglas por cuán específicas son y nunca debe reportarse como probabilidad.

Dos sesgos estructurales sobreviven a cualquier calibración de umbrales y deben declararse en cualquier publicación:

1. **La detección responde al cambio, no a la presencia.** Una chicharra que canta continuamente durante una hora produce un evento en el inicio y nada después. La ausencia de eventos es ausencia de *cambio*, no ausencia de sonido.
2. **Las reglas de transición tienen prioridad sobre las de contenido.** El primer evento de cualquier régimen acústico nuevo se etiqueta `silence_to_activity` o `activity_to_silence` sin importar la fuente. En el corpus de prueba esto absorbió la mayoría de los inicios de lluvia.

---

## Secuencia cuando lleguen las grabaciones

1. Inventario: frecuencias de muestreo, rango de fechas, coberturas, ciclo de trabajo, consistencia de reloj y zona horaria → determina si el Asunto 1 ya quedó resuelto por lo que se grabó.
2. Barrido con `--json-only` en las tres sensibilidades para ver el rendimiento de eventos por cobertura antes de comprometerse a renderizar.
3. Corrida completa con medios sobre un subconjunto representativo; anotar mediante la galería.
4. Calibrar (Asunto 2), volver a correr, volver a medir precisión y exhaustividad por rol.
5. Reconstruir el calendario fenológico y compararlo con eventos conocidos del sitio: primeras lluvias, inicios de coro observados, cualquier registro independiente del equipo de campo.
6. Solo entonces tratar `role` como etiqueta, y solo para los roles que se lo hayan ganado.
