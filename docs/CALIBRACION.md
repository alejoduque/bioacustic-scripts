# Protocolo de calibración en campo

[English](CALIBRATION.md) · **Español** · [← README](../README.md)

Todo lo que hay en este conjunto de herramientas se ha verificado hasta ahora con **audio sintético**, escrito para ejercitar rutas de código específicas. Eso demuestra que el pipeline hace mecánicamente lo que dice hacer. No dice nada sobre si los umbrales ecológicos son correctos para un sitio real.

Este documento es el plan para cerrar esa brecha cuando estén disponibles las grabaciones del bosque seco tropical. Está escrito para ser reproducible y citable: cada paso indica qué se mide, qué se decide a partir de ello y qué falsaría la decisión.

Hay dos asuntos abiertos. Todo lo demás se deriva de ellos.

---

## Primeras grabaciones de campo (Manakai, octubre 2024)

Los primeros datos reales de AudioMoth del sitio de estudio: 2.2 horas, seis de
siete archivos grabados a **192 kHz** — un despliegue ultrasónico deliberado. Dos
archivos de 60 minutos al amanecer (04:00, 05:00), más extractos cortos que quien
grabó ya había nombrado `paso murcielagos` y `buho`. Esos nombres son etiquetas
informales, y volvieron dos cosas comprobables de inmediato.

**Lo que funcionó.** En el archivo nombrado como paso de murciélagos, el modo
ultrasónico detectó `bat_echolocation` en `ultrasonic_mid` a los 102.7 s y
111.3 s — eventos breves, de 1.7 s y 3.8 s. Es la primera confirmación del modo
ultrasónico contra una grabación identificada por una persona y no contra
material sintético.

**Lo que falló, y cómo se detectó.** El archivo nombrado por el búho produjo ocho
eventos `bat_echolocation`, dos de ellos de **36 y 40 segundos**. Ningún
murciélago ecolocaliza durante 36 segundos. Renderizar esos eventos y mirarlos lo
resolvió: son bandas horizontales ininterrumpidas entre 17 y 30 kHz — un **coro de
esperanzas (katydids)**. La ecolocación genuina se ve en la misma grabación como
barridos verticales breves por encima de 40 kHz, pero no es lo que concentra la
energía de la banda.

El problema era la regla, y era el mismo error que el de la geofonía en sentido
inverso: asignaba `bat_echolocation` a *cualquier* evento cuya banda dominante
fuera ultrasónica, incluida la rama que explícitamente devolvía "actividad
ultrasónica sostenida - una jornada de forrajeo". En un bosque neotropical la
banda de 16-40 kHz está ocupada de forma continua por insectos estriduladores,
mucho más fuertes en conjunto que cualquier murciélago. El propio comentario de la
tabla de bandas decía que ahí viven las esperanzas; la regla lo ignoró.

**La corrección, a partir de las imágenes y no de una suposición.** La duración
los separa: un paso dura de uno a tres segundos, un coro dura minutos. La energía
ultrasónica sostenida (>10 s) ahora se clasifica como `insect_chorus`; los eventos
breves siguen siendo `bat_echolocation` pero con confianza 0.5 y un razonamiento
que advierte que la misma banda lleva esperanzas y que hay que verificar. En el
archivo del búho esto movió cinco eventos de murciélago a insecto y dejó intactos
los genuinamente breves.

**Sigue abierto.** Distinguir una esperanza de un murciélago *dentro* de un evento
ultrasónico breve requiere el trabajo de estructura de pulsos, hoy bloqueado por
la resolución de modulación. Hasta entonces, trate `bat_echolocation` como una
lista de candidatos por revisar, no como un conteo.

**Un límite práctico encontrado al mismo tiempo.** Los dos archivos de 60 minutos
a 192 kHz no pueden procesarse tal cual: a la frecuencia nativa con un salto de
256 muestras requieren unos 11 GB para el arreglo de magnitud más 5.5 GB para el
audio, frente a 17 GB de RAM. El análisis mantiene hoy todo el espectrograma en
memoria. Las grabaciones ultrasónicas largas necesitan procesamiento por bloques o
análisis por tramos.

---

### Ajustes calibrados para Manakai (2026-07-31)

Se barrió umbral × brecha de fusión sobre 2.1 horas de grabaciones crudas —los
dos archivos de amanecer de 60 minutos y el de atardecer—, transmitiendo cada
uno una sola vez y re-detectando contra las series en caché, de modo que 35
combinaciones cuestan apenas más que una pasada.

El primer barrido **no encontró nada utilizable**, lo cual fue informativo:
juzgaba el umbral por clips-por-hora, y en el pipeline de ventana fija esos son
controles independientes.

  umbral + brecha de fusión  deciden DÓNDE están los eventos y cuánto duran
  min_separation             decide CUÁNTOS de ellos se vuelven clips

Separados, la respuesta es clara. Para la geometría del evento —un evento debe
caber en el clip de 60 s que lo contendrá, y la cobertura debe quedar bien por
debajo del 100 % o el detector solo informa que hay sonido:

| κ | brecha | eventos/h | mediana | p90 | cobertura |
|---|---|---|---|---|---|
| 2.5 | 1.0 s | 24 | 7.4 s | 499 s | 98 % |
| 4.0 | 0.25 s | 441 | 1.2 s | 13.4 s | 84 % |
| 6.0 | 0.25 s | 668 | 0.9 s | 5.9 s | 64 % |
| **8.0** | **0.25 s** | **619** | **0.9 s** | **5.8 s** | **46 %** |
| 12.0 | 0.25 s | 498 | 0.8 s | 3.6 s | 24 % |

κ = 8.0 con una brecha de 0.25 s es el ajuste más sensible que mantiene los
eventos acotados y distinguibles — disponible como `--sensitivity dense`. Nótese
que subir κ más allá de 6 *aumenta* el conteo de eventos antes de reducirlo: un
umbral más bajo fusiona cantos vecinos en un evento largo en lugar de encontrar
más.

Luego la separación fija el presupuesto de revisión de forma independiente:

| `--min-separation` | clips/h | tiempo de revisión por hora grabada |
|---|---|---|
| 30 s | 91 | 91 min — más clip que grabación |
| 120 s | 28 | 28 min |
| **300 s** | **12** | **12 min — compresión 5:1** |
| 600 s | 6 | 6 min |

Recomendado para este sitio:

```bash
./detect_events.sh <grabaciones>/ --ultrasonic --sensitivity dense \
    --clip-duration 60 --clip-pre 30 --min-separation 300
```

En una hora de amanecer eso produce 548 eventos acotados (mediana 0.8 s, máximo
47 s) y 12 clips de un minuto, frente a 12 eventos de mediana 108 s y máximo
1780 s con los valores por defecto. **No** arregla la clasificación: 393 de esos
548 siguen cayendo a `community_shift`, y los 116 eventos `bat_echolocation`
siguen siendo candidatos y no conteos, por las razones de las secciones
anteriores.

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

## Primeros resultados externos (2026-07-30, antes de datos de campo)

El Asunto 2 ya no tiene que esperar a La Luna. `alp-data` expone **AnuraSet** —27 h de anuros neotropicales anotados por expertos en dos biomas brasileños— y el detector puede evaluarse contra ese corpus hoy mismo:

```bash
~/.bioacoustic_detector_venv/bin/pip install alp-data     # dependencia opcional
./bioacoustics.sh validate --dataset anuraset --limit 25 --sweep
```

**25 grabaciones, 266 anotaciones expertas** (mediana 0.61 s, 75 % más cortas que 2 s).

| | configuración | detecciones | precisión | exhaustividad | F1 |
|---|---|---|---|---|---|
| Por defecto | κ=2.5, mín. 2 s, fusión 5 s | 30 | 0.57 | 0.06 | **0.11** |
| Mejor del barrido | κ=3, mín. 0.25 s, fusión 0.25 s | 399 | 0.23 | 0.35 | **0.28** |

Emparejamiento por inicio con tolerancia de ±0.5 s, uno a uno. De aquí se desprenden tres cosas.

**1. Los tiempos por defecto no pueden coincidir con este corpus, por construcción.** El 75 % de las anotaciones son más cortas que `min_event_duration = 2 s`. Una exhaustividad de 0.06 con los valores por defecto es un desajuste de unidades, no una falla del detector: nosotros respondemos "¿cuándo cambió el paisaje sonoro?" y quienes anotaron respondieron "¿dónde está cada canto?". Ajustar a escala de canto mejora el F1 en 2.4×, y precisión y exhaustividad se intercambian de forma continua a lo largo de la grilla (κ=1.5, mín. 0.1 s alcanza exhaustividad 0.61 con precisión 0.14).

**2. Un F1 ≈ 0.28 es el techo honesto de un detector de cambios genérico sobre coro denso.** Es una línea base que superar, no un resultado que defender. Un modelo entrenado para la tarea rendiría mucho mejor; ese es el argumento a favor de la ruta de rasgos aprendidos.

**3. El hallazgo del clasificador es el importante — e invalida un supuesto, no un umbral.**

De las 17 detecciones que coincidieron con una anotación bajo la configuración por defecto, **16 recibieron `dominant_band = geophony`** y por lo tanto cayeron a través de todas las reglas biofónicas hasta `community_shift`. Exactitud de dominio contra un corpus que es **enteramente anuro**: **6 %**.

La causa es la tabla de bandas misma. `geophony` se define como 0–2 kHz, pero en estas grabaciones la banda por debajo de 2 kHz concentra el 97 % de la energía —ya sea por ranas que cantan grave, por agua y viento cerca de los cuerpos de agua, o por ambas cosas—. **La energía por banda por sí sola no puede separar una rana de una quebrada**, así que una regla anclada a la banda dominante asignará geofonía a un coro de anuros siempre.

Esto no podía haberse encontrado con audio sintético. Los "anfibios" sintéticos del corpus de prueba se generaron entre 2.6 y 3.1 kHz —dentro de `biophony_low`— porque eso es lo que la tabla de bandas supone. El material de prueba y el código codificaban el mismo supuesto y se daban la razón mutuamente. Solo grabaciones anotadas externamente podían romper el empate.

**Qué implica esto para las dos correcciones candidatas de abajo:** la opción (a), reajustar umbrales, no puede reparar esto — ningún umbral sobre `flatness` o `centroid` recupera una distinción que la tabla de bandas ya destruyó. El trabajo es la opción (b), y en concreto:

- calcular planitud y centroide **dentro de la banda dominante**, para que "ruidoso" se juzgue respecto del evento y no de todo el espectro
- agregar un rasgo de **estructura temporal**. Eso es lo que realmente separa los dos casos: un coro de anuros es periódico a la tasa de canto, la lluvia no lo es. La autocorrelación de la envolvente de banda, o el espectro de modulación, lo capturarían y son baratos de calcular con datos que ya están en memoria.
- tratar la banda baja como **ambigua por defecto** en lugar de como geofonía, y dejar que el rasgo temporal resuelva

---

## Intento de corrección y qué dejó establecido (2026-07-30)

La respuesta obvia al hallazgo anterior es agregar rasgos que describan la banda
propia del evento y su estructura temporal. Ambos están implementados y se
registran en `events.json`:

| Rasgo | Mide |
|---|---|
| `band_crest` | relación pico-media del espectro medio dentro de la banda dominante |
| `band_entropy` | entropía normalizada entre los bins de esa banda — disperso vs concentrado |
| `band_centroid` | dónde se ubica la energía dentro de su propia banda |
| `periodicity` / `pulse_rate_hz` | modulación de amplitud medida **dentro del evento** |
| `context_periodicity` / `context_rate_hz` | lo mismo sobre una ventana de ≥4 s **alrededor** del evento |

**No están conectados a la clasificación, y no deberían estarlo hasta repetir la
medición de abajo con los datos que faltan.** Registrarlos no cuesta nada y le da
a la calibración futura rasgos reales que ajustar.

### Medido sobre 60 grabaciones de AnuraSet

186 detecciones que coinciden con una anotación experta de anuros, frente a 202
detecciones de archivos de AnuraSet sin anotación alguna:

| | anuros (n=186) | sin anotar (n=202) |
|---|---|---|
| `band_crest` mediana | 35.06 | 35.61 |
| `band_entropy` mediana | 0.271 | 0.214 |
| `periodicity` mediana | 0.000 | 0.112 |

**Ninguna separación. En periodicidad el orden está invertido.** En todos los
umbrales probados, la clase negativa se retuvo en igual o mayor proporción que la
positiva.

### Por qué esto es inconcluyente y no una refutación

Tres defectos del experimento, todos identificados a partir de los números:

1. **La clase negativa no contiene lluvia.** Los "archivos de AnuraSet sin
   anotación de anuros" son grabaciones nocturnas junto a cuerpos de agua; lo que
   contienen es sobre todo *insectos*, más tonales y mucho más regularmente
   pulsados que las ranas. Eso explica directamente la periodicidad invertida. El
   experimento comparó ranas contra otra biofonía, no contra clima.
2. **Una tasa de repetición no puede medirse dentro de una sola repetición.** A
   62.5 marcos por segundo, una detección de 0.25 s son 15 marcos: insuficientes
   para contener dos ciclos de algo más lento que ~4 Hz. Medido directamente: un
   coro sintético de 3 Hz puntúa 0.000 en una ventana de 0.25 s, 0.675 en 0.5 s y
   1.000 desde 2 s en adelante. La mediana de `periodicity` de 0.000 en anuros es
   ese artefacto.
3. **La tasa de marcos de la envolvente limita qué modulación es visible.**
   Muestrear la envolvente de banda cada 512 muestras resuelve modulación solo
   hasta ~31 Hz, por debajo de las tasas de pulso típicas de anuros. Los valores
   intra-evento se agrupan en 15.6 Hz, el borde del rango de búsqueda: señal de
   estar tocando el límite, no de estar midiéndolo.

Una versión anterior de la medida de periodicidad era simplemente incorrecta, y
el material sintético lo ocultaba: la lluvia sintética puntuaba **0.93**, más alto
que cualquier coro real, porque se genera como ruido multiplicado por una ventana
de Hann y una envolvente suave autocorrelaciona cerca de 1.0 en todos los
desplazamientos. Quitar la tendencia no lo resolvió — la autocorrelación
normalizada es invariante a escala, así que encoger el residuo no lo vuelve menos
suave. La medida ahora toma la *prominencia del primer pico local*, que evalúa la
propiedad que de verdad importa: la autocorrelación de un tren de pulsos vuelve a
subir en el período, la de un vaivén simplemente decae. El material con ventana de
Hann ahora puntúa 0.000 y un tren de pulsos de 5 Hz, 1.000.

### Qué hace falta para terminar esto

- **Un corpus de geofonía etiquetado.** `AudioSet` está registrado en `alp-data`
  pero no trae rutas de particiones, así que no es utilizable tal cual.
  Grabaciones de lluvia y viento con etiquetas —ESC-50, FSD50K, o grabaciones de
  campo anotadas en el sitio— permitirían correr la comparación real. Este es el
  bloqueo.
- **Modulación medida a la resolución correcta**, ya sea con un salto más fino
  solo para la envolvente o con un espectro de modulación propiamente dicho, para
  que las tasas de pulso por encima de 31 Hz sean visibles.
- **Y entonces** ajustar umbrales y volver a correr `validate` para confirmar que
  la exactitud de dominio del 6 % efectivamente se mueve.

Hasta entonces la posición honesta es la que se enuncia abajo: `dominant_band` y
los rasgos numéricos son confiables, `role` es una hipótesis.

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
