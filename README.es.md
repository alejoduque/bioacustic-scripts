# Bioacoustic Scripts

[English](README.md) · **Español**

Un conjunto de herramientas para convertir grabaciones de campo de AudioMoth en **datos fenológicos que puedan gobernarse por OSC**.

Escucha los momentos en que el paisaje sonoro cambia — una especie que arranca, la lluvia que llega, el coro del amanecer que se releva —, recorta un video corto de cada uno, lo clasifica por rol ecológico y acumula esos eventos en un calendario fechado que un instrumento puede seguir: Eurorack, láser ILDA, SuperCollider, cualquier cosa que hable OSC.

**Galería en vivo:** https://etc.altred.xyz/staticbioacustics/index.html
**Protocolo de calibración en campo:** [docs/CALIBRACION.md](docs/CALIBRACION.md) — qué hacer cuando lleguen las grabaciones reales

---

## Cómo ejecutarlo

### La primera vez

```bash
git clone git@github.com:alejoduque/bioacustic-scripts.git
cd bioacustic-scripts
chmod +x bioacoustics.sh detect_events.sh
./bioacoustics.sh
```

Esa es toda la instalación. En el primer arranque el script busca un intérprete de Python 3.10+, crea un entorno virtual en `~/.bioacoustic_detector_venv` e instala allí `numpy`, `scipy`, `soundfile`, `metamoth` y `python-osc`. Toma un par de minutos una sola vez; las corridas siguientes arrancan de inmediato. No se instala nada a nivel de sistema y no hay nada más que configurar.

Dos cosas que conviene saber antes de empezar:

- **ffmpeg es opcional pero recomendable.** Sin él igual se obtienen clips, `events.json`, exportaciones OSC, el calendario y los reportes; lo que no se obtiene es video de espectrograma, imágenes fijas ni GIFs. `brew install ffmpeg` (macOS) o `sudo apt install ffmpeg` (Debian/Ubuntu).
- **Los nombres de archivo importan para la fenología.** El formato AudioMoth `YYYYMMDD_HHMMSS.WAV` es la vía por la que la herramienta sabe cuándo se hizo cada grabación. Archivos con otro nombre igual producen eventos y clips, pero no pueden ubicarse en un calendario.

Revisar el entorno en cualquier momento:

```bash
./bioacoustics.sh doctor
```

### La vía guiada

```bash
./bioacoustics.sh
```

Un solo punto de entrada, un solo menú:

```
 1  Detectar eventos y recortar clips        el pipeline principal — empiece aquí
 2  Calendario fenológico                    series ecológicas fechadas + OSC
 3  OSC                                      transmitir, servir o exportar
 4  Galería de clips por evento              recorrer los clips por tipo
 5  Reporte de metadatos AudioMoth           cabeceras, temperatura, batería
 6  Utilidades de medios                     espectrograma completo, GIF, partir
 7  Lote HDR de fotos (DJI DNG)              fijas horquilladas del mismo muestreo
 8  Revisión del entorno                     qué está instalado
```

Cada opción explica qué hace y luego pregunta solo lo que no puede inferir: dónde están las grabaciones, qué tan sensible debe ser la detección, de qué tipos de evento se quieren clips, si se renderiza video. Los valores por defecto aparecen entre corchetes, así que Enter los acepta. Antes de ejecutar cualquier cosa se muestra un plan para confirmar:

```
Plan
    recordings : 11 file(s)
        output : ./detected_events
   sensitivity : balanced (threshold 2.5 MAD)
  clip padding : -20s / +10s
       domains : all
   event types : all
         media : video, still, reels
     phenology : yes

Run this? (Y/n)
```

Las respuestas se guardan en `~/.bioacoustics_wizard.json`, de modo que la segunda sesión es sobre todo presionar Enter. Escribir `q` dentro de un flujo devuelve al menú; `q` en el menú termina. Nada es destructivo: cada flujo escribe en una carpeta de salida que usted elige.

### La vía directa

Cada función es también un subcomando, para automatizar y repetir:

```bash
# Analizar una carpeta: clips, videos, OSC, calendario, galería
./detect_events.sh grabaciones/ --phenology

# Lo mismo, explícito
./bioacoustics.sh detect grabaciones/ --phenology -o ./resultados

# Una grabación, más sensible, sin video
./detect_events.sh grabaciones/20250315_053000.WAV --sensitivity subtle --no-video

# Solo lluvia y viento, con vistas previas en GIF
./detect_events.sh grabaciones/ --domains geophony --gif

# Transmitir el calendario a un instrumento, un día por segundo, en bucle
./bioacoustics.sh osc phenology ./resultados --loop

# Que el instrumento pregunte en vez de recibir empujones: responde /phenology/query/*
./bioacoustics.sh osc serve ./resultados --listen-port 57121

# Reconstruir salidas sin volver a analizar el audio
./bioacoustics.sh phenology ./resultados
./bioacoustics.sh gallery ./resultados
```

Ayuda de cualquier subcomando:

```bash
./bioacoustics.sh --help
./bioacoustics.sh detect --help
```

Una ruta como primer argumento equivale a `detect`, de modo que `./detect_events.sh rec.WAV --threshold 1.5` sigue funcionando como siempre.

### Cuatro flujos de trabajo típicos

**Revisar una tarjeta de grabaciones.** La detección es el paso costoso; todo lo demás lee su salida.

```bash
./detect_events.sh /Volumes/AUDIOMOTH/ -o ./luna_marzo --phenology
open ./luna_marzo/gallery.html          # recorrer los clips por tipo de evento
open ./luna_marzo/summary_report.html   # el lote de un vistazo
```

**Ajustar la sensibilidad antes de comprometerse a una corrida larga.** `--json-only` reporta qué se detectaría sin escribir clips ni renderizar video: el mismo análisis, una fracción del tiempo y del disco cuando ffmpeg entra en juego. (En una prueba de 11 × 100 s: 80 KB de JSON en lugar de 155 MB de medios.)

```bash
./detect_events.sh grabaciones/ --sensitivity salient --json-only -o /tmp/probe
./detect_events.sh grabaciones/ --sensitivity subtle  --json-only -o /tmp/probe2
# comparar el conteo de eventos y volver a correr en serio con lo que convenza
```

El análisis espectral es el costo fijo y corre de todas maneras, así que el ahorro está en el renderizado, no en la escucha.

**Seguir una temporada fenológicamente.** Apúntelo a todo lo que tenga; el calendario necesita grabaciones de al menos dos días.

```bash
./detect_events.sh "Epoca lluvias/" -o ./temporada --phenology --days-per-second 2
open ./temporada/phenological_calendar.html
column -s, -t ./temporada/phenological_series.csv | less -S
```

**Alimentar una instalación.** Analizar una vez y luego transmitir o servir cuantas veces se quiera.

```bash
./detect_events.sh temporada/ -o ./temporada --phenology
cat ./temporada/osc_address_map.txt                   # lo que va a recibir
./bioacoustics.sh osc phenology ./temporada --loop --host 192.168.1.40 --port 57120
```

---

## Cómo leer un clip de espectrograma

Cada clip renderizado codifica cuatro canales de información independientes. Nada es decorativo.

| Canal | Transporta | Definido por |
|---|---|---|
| **Eje vertical** | frecuencia — qué parte del espectro ocupa el sonido | `--max-freq`, o Nyquist en modo ultrasónico |
| **Eje horizontal** | tiempo dentro del clip, desplazándose de derecha a izquierda | duración del clip = evento + margen previo/posterior |
| **Brillo** | energía en dBFS sobre un rango de 72 dB, escala logarítmica | `dynamic_range`, `gain_scale` |
| **Matiz (color)** | el **dominio acústico** que asignó el clasificador | `domain_colors` en `config.py` |

El texto es blanco con un contorno negro de 1 píxel y sin caja de fondo, para que se lea sobre cualquier mapa de color sin tapar el espectrograma que hay debajo — y para que el color en el cuadro signifique exactamente una cosa: el dominio acústico.

### La leyenda separa medición de inferencia

La fila inferior lleva dos tipos distintos de afirmación, en lados opuestos, para que nunca se lean como una sola:

```
unclassified                    geophony  15.2 kHz  0.3s  NDSI -0.58  ACI 235
candidate: insect chorus (40%)  ultrasonic mid  27.7 kHz  5.8s  13 Hz pulse  NDSI +0.78  ACI 327
probable: dawn chorus participant (80%)   biophony mid  5.4 kHz  5.0s  NDSI +1.00  ACI 446
```

**Derecha — medido.** Banda dominante, centroide espectral, duración, tasa de pulso cuando la envolvente es lo bastante periódica para significar algo, y los índices. Todo aritmética sobre la señal.

**Izquierda — inferido**, etiquetado según hasta dónde llega la afirmación:

| Etiqueta | Significa |
|---|---|
| `probable` | una regla específica coincidió en varios rasgos (confianza ≥ 0.6) |
| `candidate` | una regla coincidió, pero se sabe que sobre-afirma — `bat_echolocation` está aquí, porque la misma banda lleva esperanzas |
| `unclassified` | ninguna regla coincidió; el evento cayó a la rama de respaldo y la etiqueta no significa más que eso |

Esto existe porque la validación estableció que `role` es una hipótesis de umbrales sin calibrar mientras que `dominant_band` es una medición. Imprimir `Community Shift (20%)` le daba a la rama de respaldo apariencia de hallazgo; ahora imprime `unclassified`. El nivel viaja con el evento como campo `certainty` en `events.json` y como distintivo en cada tarjeta de la galería.

### Por qué el color corresponde al dominio

Un mapa de color es una señal categórica, y solo hay una decisión categórica en la que valga la pena gastarlo. La frecuencia ya es el eje vertical; la amplitud ya es el brillo. Lo que ningún eje muestra es **qué tipo de participante** produjo el sonido, y eso es justamente el propósito de la clasificación.

Así, el mapa de color responde "¿quién habla?" de un vistazo, antes de leer una sola etiqueta:

| Dominio | Mapa de color | Se lee como | Qué vive ahí |
|---|---|---|---|
| **biofonía** | `green` | vivo, vegetal | aves, anuros, insectos, murciélagos — todo lo vivo |
| **geofonía** | `cool` (azul/verdeazulado) | agua, aire, frío | lluvia, viento, truenos, agua corriente |
| **antrofonía** | `fiery` (naranja/rojo) | intrusión, alarma | motores, aviones, maquinaria |
| **transición** | `magma` (rosa/violeta) | un borde, no una voz | el paisaje sonoro cambiando de estado |

Al recorrer una carpeta de clips, un ensamblaje se lee como una distribución de color: una noche verde es una noche biofónicamente activa, una noche azul se la llevó la lluvia, el naranja indica que se oía una vía o una bomba. Esa propiedad es lo que hace la galería recorrible a lo largo de cientos de eventos, y es la razón por la que el color corresponde al dominio y no al rol. Dieciséis roles exigirían dieciséis mapas de color que nadie podría distinguir; cuatro dominios se separan de un vistazo.

Las transiciones reciben `magma` deliberadamente. No son una voz: marcan la *costura* donde una comunidad acústica cede el lugar a otra. Darles un matiz que no pertenece ni al verde vivo ni al azul elemental mantiene visible esa distinción.

### La cadena que va de la FFT al color

El color es el último eslabón de una cadena que empieza en las muestras crudas. Cada paso es una decisión tomada a partir del anterior, y nada en ella es una identificación de especie:

```
muestras
  → magnitud STFT |X(t,f)|            frame_size 2048, hop 512, Hann
  → flujo espectral Φ(t)              norma L2 rectificada de media onda entre marcos
  → umbral adaptativo                 mediana + 2.5 × 1.4826 × MAD, ventana causal 60 s
  → inicio/fin del evento             marcos contiguos sobre el umbral, fusionados y filtrados
  → rasgos por evento                 energías por banda, centroide, planitud, duración, índices
  → ROL ecológico                     basado en reglas, 16 categorías      (la leyenda)
  → DOMINIO acústico                  rol → {biofonía, geofonía, antrofonía, transición}
  → MAPA DE COLOR                     dominio → {green, cool, fiery, magma}
```

El **rol** es el juicio más fino que hace el sistema, y la leyenda lo imprime con una confianza (`Dawn Chorus Participant (80%) | biophony mid`). El **dominio** es la agregación gruesa y robusta: una lluvia mal archivada como viento sigue siendo geofonía, sigue siendo azul. Por lo tanto el color es más confiable que la leyenda que lo acompaña, y esa es exactamente la razón por la que el color lleva el significado de un vistazo y la leyenda lleva el detalle.

### Dos ejemplos trabajados

Son cuadros reales del corpus de verificación, y cada uno es internamente consistente: se puede contrastar la clasificación contra la imagen y los números contra ambas.

**Un participante del coro del amanecer, en verde.**

Dos barridos recorren de 4.7 a 6.7 kHz sobre un fondo casi silencioso. La energía cae de lleno en `biophony_mid` (4–8 kHz, la banda de los paseriformes); la marca temporal de la grabación es 05:30, dentro de la ventana del amanecer de 04:00–07:00; los barridos son tonales, así que la planitud es baja. Las reglas se disparan en ese orden y producen `dawn_chorus_participant` con confianza 0.80, dominio biofonía, mapa de color verde. La leyenda dice `Dawn Chorus Participant (80%) | biophony mid`, y `NDSI +1.00` lo confirma: prácticamente toda la energía está en la banda biofónica de 2–8 kHz y nada en la banda antropogénica de 1–2 kHz.

**Un aguacero, en magma — y por qué no se etiqueta `rain_event`.**

Un bloque sólido de ruido llena todo por debajo de ~1.9 kHz durante todo el clip, sin nada por encima. `dominant_band` es `geophony` (0–2 kHz) y `NDSI −0.99` concuerda: esencialmente toda la energía está en la banda baja que el índice considera no biofónica. La imagen y la aritmética coinciden perfectamente.

La etiqueta, sin embargo, dice `Silence To Activity (70%) | geophony`, y el clip se renderiza en magma de transición y no en azul de geofonía. Dos reglas se combinan para producir eso:

1. **Las reglas de transición tienen prioridad sobre las de contenido.** Cuando el flujo pico de un evento supera en más de 5× al del evento anterior, se archiva como `silence_to_activity` sin importar qué produzca el sonido. El inicio de un aguacero es exactamente ese salto. Es deliberado —la costura entre regímenes acústicos es ecológicamente interesante—, pero implica que el primer evento de cualquier régimen nuevo suele ser una transición.
2. **La regla de `rain_event` tampoco se disparó en los eventos posteriores, que ya no eran un salto.** Requiere `flatness > 0.30`; la planitud medida de esos bloques fue de **0.21 y 0.29**.

El segundo punto es una brecha de calibración que conviene conocer antes de confiar en las etiquetas de forma masiva, y proviene de una propiedad de los rasgos y no de un error de código:

- **La planitud espectral se calcula sobre todo el espectro.** Una señal perfectamente ruidosa *dentro de su propia banda* obtiene un valor bajo si ocupa solo una parte del rango. La medida responde a "¿es ruidosa esta grabación?", no a "¿es ruidoso este evento?".
- **El centroide espectral se pondera por magnitud sobre todo el espectro**, de modo que un piso de ruido amplio y de bajo nivel lo arrastra hacia arriba. Esos mismos eventos de lluvia reportaron centroides de **6.5 y 7.7 kHz** pese a no tener energía alguna por encima de 2 kHz, razón por la cual la regla de antrofonía (`centroid < 1500`) tampoco los capturó.

En el corpus de verificación de 45 eventos, `rain_event`, `wind_event`, `water_flow`, `mechanical_intrusion` y `aircraft_passage` **nunca se emitieron**. El contenido geofónico era real, visible y estaba correctamente medido: simplemente cayó a las reglas de transición y de respaldo.

Los umbrales viven al inicio de `classifier.py` como constantes con nombre (`GEOPHONY_FLATNESS`, `ANTHROPHONY_CENTROID_HZ`, …) precisamente para poder recalibrarlos contra grabaciones de campo anotadas. **Mientras esa calibración no ocurra sobre datos reales de bosque seco tropical, trate `dominant_band` y los rasgos numéricos como la señal confiable, y `role` como una hipótesis.** Por la misma razón, el color del dominio es más confiable que la leyenda que lo acompaña.

Ver [docs/CALIBRACION.md](docs/CALIBRACION.md) para el protocolo completo.

---

## Ultrasonido: murciélagos, Nyquist y lo que se descarta

El AudioMoth graba a 8, 16, 32, 48, 96, 192, 250, 256 o 384 kHz. Cualquier cosa por encima de 48 kHz es una decisión deliberada de grabar murciélagos, y eso cambia lo que la herramienta debe hacer.

### El límite duro

Muestrear a una frecuencia *fs* permite representar frecuencias solo hasta **Nyquist = fs/2**. Por encima de eso el contenido no desaparece: hace **aliasing**, se pliega a `|fs − f|` y aparece en una frecuencia que nunca estuvo presente:

| Frecuencia AudioMoth | Nyquist | Alcanza | No alcanza |
|---|---|---|---|
| 48 kHz | 24 kHz | aves, anuros, insectos, los murciélagos más graves | casi toda la ecolocación |
| 96 kHz | 48 kHz | Molossidae, algunos Vespertilionidae | Phyllostomidae agudos |
| 192 kHz | 96 kHz | casi toda la ecolocación neotropical | las especies CF más agudas |
| 256 / 384 kHz | 128 / 192 kHz | todo | — |

No es hipotético. Al construir el corpus de prueba se escribió un emisor sintético de 105 kHz en un archivo de 192 kHz; apareció en 87 kHz (`|192 − 105|`) y fue clasificado a partir de esa frecuencia. Una especie real por encima de Nyquist produce exactamente el mismo artefacto, y nada aguas abajo puede notar la diferencia. **Elija la frecuencia de muestreo según el ensamblaje que espera, y desconfíe de la energía pegada al borde superior del gráfico.**

### Por qué el modo por defecto descarta el ultrasonido

Por defecto el detector submuestrea a 48 kHz antes de analizar. Es la decisión correcta para un muestreo de aves y anuros —acota el costo y ajusta la resolución de la STFT a las sílabas de las aves— pero el filtro antialias elimina todo lo que está por encima de 24 kHz **de forma permanente para ese análisis**. Los murciélagos se vuelven invisibles: no aparecen como eventos débiles, no aparecen en absoluto.

En lugar de fallar en silencio, una grabación muestreada por encima del doble de la frecuencia de análisis dispara una advertencia:

```
! This recording carries content up to 96 kHz, but analysis downsamples to 48 kHz.
  Everything above 24 kHz — bat echolocation, high katydids — is discarded.
  Re-run with --ultrasonic to analyse at the native rate.
```

### Qué cambia `--ultrasonic`

```bash
./detect_events.sh grabaciones/ --ultrasonic
```

Cuatro cosas se mueven juntas, porque cambiar una sola deja a los murciélagos inutilizables:

| | Por defecto | `--ultrasonic` | Por qué |
|---|---|---|---|
| Frecuencia de análisis | 48 kHz | nativa (192 kHz…) | de otro modo se filtra todo lo que supera Nyquist/2 |
| Ventana STFT | 2048 / salto 512 | 1024 / salto 256 | a 192 kHz una ventana de 2048 abarca 10.7 ms — más que una llamada entera |
| Tabla de bandas | 5 bandas hasta 24 kHz | 7 bandas hasta 160 kHz | `ultrasonic` a secas no separa un Molossidae de un Phyllostomidae |
| Tiempos del evento | fusión 5 s, mín. 2 s | fusión 1 s, mín. 0.3 s | un paso dura 1–3 s; los valores audibles funden una noche de forrajeo en un solo bloque |

Los parámetros explícitos `--merge-gap` / `--min-event-duration` tienen prioridad sobre los valores del modo.

El video también se reencuadra: el eje llega hasta Nyquist en vez de 10 kHz y pasa a una escala de frecuencia **logarítmica**, para que 0–10 kHz siga ocupando una porción legible de un gráfico de 0–96 kHz en lugar de quedar aplastado en el 10 % inferior.

### La tabla de bandas ultrasónicas

Cortes elegidos para ensamblajes de bosque seco neotropical:

| Banda | Rango | Ocupantes típicos |
|---|---|---|
| `ultrasonic_low` | 16–40 kHz | Molossidae, algunos Vespertilionidae, esperanzas (katydids) agudas |
| `ultrasonic_mid` | 40–80 kHz | la mayoría de llamadas de búsqueda de Vespertilionidae y Phyllostomidae |
| `ultrasonic_high` | 80–160 kHz | Phyllostomidae de alta frecuencia, zumbidos terminales de alimentación |

Un evento cuya banda dominante sea cualquiera de estas se clasifica como `bat_echolocation` (dominio biofonía, por lo que se renderiza en verde). Esa regla se evalúa *antes* que las reglas dieles, porque una banda dominante por encima de 16 kHz es inequívoca: ninguna ave, anuro o motor pone ahí su energía principal.

Verificado sobre una grabación sintética de 192 kHz con cuatro fuentes deliberadamente distintas:

| Sintetizado | Detectado en | Banda | Rol |
|---|---|---|---|
| Barridos FM 60→25 kHz + zumbido de alimentación | 0.07 s | `ultrasonic_mid` | `insect_chorus` * |
| Tono CF de 85 kHz | 10.34 s | `ultrasonic_high` | `bat_echolocation` |
| Banda de esperanza a 12 kHz | 14.05 s | `biophony_high` | `insect_chorus` |
| Barridos 30→18 kHz | 24.00 s | `ultrasonic_low` | `bat_echolocation` |
| Segundo paso 60→25 kHz | 17.40 s | `ultrasonic_mid` | `bat_echolocation` |

\* Esta detección fusiona la banda de esperanza con los barridos de murciélago en
un solo evento de 5.8 s, y la energía ultrasónica sostenida ahora se lee como coro
de insectos y no como ecolocación — ver el hallazgo de campo abajo. La banda es
correcta; el rol refleja lo más largo de las dos cosas dentro del evento fusionado.

El mismo archivo analizado **sin** `--ultrasonic` arrojó dos eventos `insect_chorus` y ningún murciélago: las esperanzas sobrevivieron al submuestreo, todo lo demás se filtró.

### Costo

Analizar a 192 kHz con un salto de 256 muestras produce 750 marcos por segundo, ocho veces el valor audible por defecto. La línea base adaptativa es una mediana móvil sobre una ventana de 60 segundos, que es O(marcos × ventana): a esa tasa, una hora de grabación tomaría días. Por eso se evalúa en hasta 2000 puntos de anclaje y se interpola linealmente entre ellos, calculando siempre de forma exacta los primeros 512 marcos (es el único tramo donde el estadístico se mueve rápido de verdad, mientras la ventana aún se está llenando).

La aproximación se contrastó contra el cálculo exacto en todo el corpus audible: **conteos de eventos idénticos, inicios idénticos y dos finales de evento de 45 que difieren en 32 ms y 75 ms** — un cruce de umbral sobre una cola decreciente que cae uno o dos marcos más allá. La aceleración es de 5.6× a 48 kHz, y a 192 kHz es la diferencia entre utilizable e inutilizable.

---

## Por qué eventos y no grabaciones

Las versiones anteriores renderizaban un espectrograma por grabación. Un ensamblaje de anuros de doce segundos dentro de una hora de cinta es invisible así, y no hay nada a lo que apuntar un instrumento.

El pipeline ahora trabaja por evento:

```
audio → rasgos espectrales → detección por umbral adaptativo → clasificación
      → un clip por evento (con contexto) → video de espectrograma, fija, GIF
      → un reel por tipo de evento → events.json → OSC → reporte
```

y luego entre grabaciones:

```
resultados → calendario fenológico → partitura OSC / transmisión / servidor de consultas
           → galería de eventos → resumen del lote
```

Los clips se archivan por lo que son, de modo que cada tipo de voz obtiene su propia carpeta de evidencia:

```
detected_events/
  20250315_053000/
    events.json                     # metadatos completos: eventos, clasificaciones, índices
    events.osc                      # paquete OSC temporizado de esta grabación
    events_score.scd                # partitura SuperCollider
    report.html                     # reporte por grabación
    clips/
      biophony/dawn_chorus_participant/
        event_003_dawn_chorus_participant_40.8s-45.8s.wav
        event_003_dawn_chorus_participant_40.8s-45.8s.mp4
        event_003_..._-spectrogram.png
        event_003_..._-thumbnail.png
      geophony/rain_event/…
      transition/community_shift/…
    reels/
      reel_dawn_chorus_participant.mp4    # todos los clips de un tipo, concatenados
  phenological_calendar.json        # el calendario, incl. marcos OSC por día
  phenological_calendar.html        # mapa de calor, series CV, deriva del amanecer
  phenological_series.csv           # una fila ordenada por día
  phenology.osc                     # paquete OSC temporizado de toda la temporada
  phenology_score.scd               # partitura SuperCollider de la temporada
  osc_address_map.txt               # referencia de direcciones, generada
  gallery.html                      # todos los clips, agrupados por tipo de evento
  summary_report.html               # el lote de un vistazo
```

Los videos de evento se codifican por color según el dominio acústico —biofonía verde, geofonía fría, antrofonía ígnea, transiciones magma— y se rotulan con cobertura, fecha, desplazamiento dentro de la grabación, rol ecológico, confianza, banda dominante, NDSI y ACI.

---

## Datos fenológicos por OSC

Este es el propósito de la herramienta. Una temporada de grabaciones se convierte en un flujo de control.

```bash
# Reproducir 90 días de grabación de campo en 90 segundos
./bioacoustics.sh osc phenology detected_events/ --days-per-second 1

# Modo instalación: repetir hasta detener
./bioacoustics.sh osc phenology detected_events/ --loop --port 57120

# Que el instrumento pregunte en vez de recibir empujones
./bioacoustics.sh osc serve detected_events/ --listen-port 57121
```

**Cada escalar se envía dos veces** —el valor ecológico crudo y luego el mismo valor escalado a 0–1 sobre todo el conjunto—, para que un patch pueda tomar números absolutos o un voltaje de control sin conocer el rango de la temporada:

```
/phenology/day              0  "2025-03-10"  69          índice, fecha, día del año
/phenology/day/activity     5.0   1.0                    eventos por grabación, cv
/phenology/day/richness     8.0   1.0                    roles distintos, cv
/phenology/day/biophony     0.75  0.75                   proporción de eventos, cv
/phenology/day/ndsi         0.93  0.96                   índice de paisaje sonoro, cv
/phenology/day/dawn         330.7 0.70                   inicio del coro (min), cv
/phenology/day/hourly       0 0 0 0 0 6 0 …              24 enteros
/phenology/day/role         "amphibian_assembly" 4 0.20  rol, conteo, proporción
/phenology/event            "breeding_chorus_onset" "2025-03-14" 73  2.1
/phenology/diel/table       0.0 0.0 … 0.94 …             24 flotantes: tabla de onda diel
/phenology/range/<campo>    min max                      la normalización empleada
```

Campos normalizados: `activity`, `richness`, `biophony`, `geophony`, `anthrophony`, `ndsi`, `adi`, `aci`, `dawn`.

El servidor de consultas responde a `/phenology/query/meta`, `/query/day <int>`, `/query/date <str>`, `/query/next`, `/query/prev`, `/query/events` y `/query/reply_port <int>`.

También se emite OSC por evento (`/parliament/event/*`), incluyendo `/parliament/event/voct` —el centroide espectral ya convertido a V/Oct con 261.63 Hz en 0 V— más `/ilda/{color,intensity,angle,speed}` para control de láser.

El mapa completo de direcciones se escribe junto a los resultados como `osc_address_map.txt`, generado desde el código en lugar de copiado aquí:

```bash
./bioacoustics.sh osc map detected_events/
```

**Cambios fenológicos detectados entre días:** `breeding_chorus_onset` (la energía biofónica baja y alta suben a la vez), `migration_acoustic_shift` (recambio de ADI), `rain_season_transition` (aumentan los eventos geofónicos), `dawn_chorus_advance_delay` (se desplaza la hora de inicio), `nocturnal_community_change` (se releva el ensamblaje nocturno).

---

## Referencia de comandos

```
./bioacoustics.sh [subcomando] [opciones]

  detect      analizar grabaciones → clips, videos, OSC, reportes
  phenology   construir/actualizar el calendario y sus exportaciones OSC
  osc         export | phenology | events | serve | map
  gallery     reconstruir la galería a partir de resultados existentes
  media       spectrogram | poster | split | gif
  metadata    reporte de metadatos AudioMoth
  validate    evaluar el detector contra corpus anotados externamente
  doctor      revisar herramientas y reportar qué hay disponible
  wizard      la interfaz guiada (por defecto si no se pasan argumentos)
```

Una ruta como primer argumento equivale a `detect`, así que `./detect_events.sh rec.WAV --threshold 1.5` sigue funcionando.

### detect

```
  -o, --output-dir DIR        dónde van los resultados (./detected_events)
      --sensitivity NAME      subtle | balanced | salient | dense
      --threshold N           umbral de flujo espectral en unidades MAD (2.5)
      --pre-roll N            segundos de contexto antes del inicio (20)
      --post-roll N           segundos de contexto después del final (10)
      --baseline-window N     ventana de la línea base adaptativa (60)
      --min-event-duration N  descartar eventos más cortos (2)
      --merge-gap N           fusionar eventos más cercanos que esto (5)
      --max-clip-duration N   tope de duración del clip en segundos (300)
      --ultrasonic            analizar a la frecuencia nativa, extender las
                              bandas para cubrir ecolocación y ajustar los
                              tiempos a la escala de un murciélago. Necesario
                              para grabaciones por encima de 48kHz; sin esto
                              todo lo que supere 24kHz se descarta.

      --roles LIST            recortar solo estos tipos de evento
      --domains LIST          biophony,geophony,anthrophony,transition
      --min-confidence N      omitir clasificaciones por debajo de esto (0-1)

      --organize-by MODE      role | domain | flat
      --max-freq N            frecuencia superior del espectrograma (10000)
      --no-video              omitir el renderizado MP4
      --no-poster             omitir PNG + miniatura
      --gif                   además, un GIF en bucle por clip
      --no-reels              omitir los reels concatenados por tipo
      --no-style-by-domain    un solo mapa de color para todos los eventos
      --no-gallery            omitir gallery.html
      --json-only             solo metadatos — sin clips, medios ni reportes

      --phenology             construir el calendario al terminar
      --days-per-second N     ritmo de reproducción grabado en las exportaciones OSC (1)
      --no-csv                omitir la exportación CSV

      --osc-live              reproducir los eventos en vivo a medida que se hallan
      --osc-host / --osc-port destino OSC (127.0.0.1 : 57120)
      --no-osc                omitir la salida OSC y SuperCollider
```

Los tres preajustes de sensibilidad y lo que modifican están tabulados en [Detección de eventos](#detección-de-eventos).

---

## Scripts reemplazados

Todo lo de abajo sigue funcionando; cada uno reenvía ahora al pipeline unificado e imprime el comando que lo sustituye.

| Script anterior | Ahora | Qué cambió |
|---|---|---|
| `make-spectrogram-movie-fixed.sh` | `bioacoustics.sh media spectrogram` | La misma cadena de filtros. Los clips por evento son la vía por defecto; esto es la salida de emergencia para archivo completo. Las leyendas ya no se rompen con comas ni dos puntos en los nombres de cobertura. |
| `make-spectrogram-thumbnail-fixed.sh` | `bioacoustics.sh media poster` | La misma receta de `showspectrumpic`, ahora aplicada también por clip. Las miniaturas son de 256×144 (antes 128×72). |
| `master_script.sh` | `bioacoustics.sh detect` | Tres scripts encadenados se volvieron etapas de un pipeline, operando sobre eventos en vez de grabaciones completas. |
| `enhanced_html_generator.sh` | `bioacoustics.sh gallery` | Era idéntico byte a byte al archivo siguiente. Una tarjeta por evento agrupada por rol; lee `events.json` en lugar de rastrear `*-thumbnail.png`; lightbox autocontenido; sin dependencia de ffprobe/jq/numfmt. El etiquetado GPS se conservó, con la misma clave de `localStorage`. |
| `make-html-lightbox-table-fixed.sh` | `bioacoustics.sh gallery` | Duplicado del anterior (mismo md5). |
| `vid2gif.sh` | `bioacoustics.sh media gif` | `palettegen`/`paletteuse` de ffmpeg en lugar de mplayer + ImageMagick + gifsicle. Sin volcado de marcos temporales, sin rutas fijas a `/opt/homebrew`. |
| `split-video.sh` | `bioacoustics.sh media split` | El mismo enfoque de presupuesto de tamaño, sin dependencia de `bc`, con el audio recodificado para que cada parte se reproduzca por separado. |

Sin cambios y accesibles desde el asistente: `AudioMothRECS_LaLuna/audiomoth_processing.sh` (reporte de metadatos) y `HDR-DNG-DJI-IMGS` (DNG horquillado → HDR).

---

## Cómo funciona la detección

### Análisis espectral

El audio se mezcla a mono, opcionalmente se submuestrea (polifásico, `scipy.signal.resample_poly`) y luego se transforma marco a marco:

$$X(t,k) = \sum_{n=0}^{N-1} x(tH + n)\,w(n)\,e^{-2\pi i kn/N}$$

con **N = frame_size = 2048**, **H = hop_size = 512** (75 % de solapamiento) y *w* una ventana de Hann periódica. Solo se conserva la mitad real, lo que da `N/2 + 1 = 1025` bandas.

La resolución se desprende directamente de *N*, *H* y la frecuencia:

| | 48 kHz (por defecto) | 192 kHz + `--ultrasonic` |
|---|---|---|
| Resolución en frecuencia `fs/N` | 23.4 Hz | 187.5 Hz |
| Longitud de ventana `N/fs` | 42.7 ms | 5.3 ms |
| Separación entre marcos `H/fs` | 10.7 ms | 1.3 ms |

El valor por defecto está ajustado a las sílabas de las aves (50–200 ms); el ajuste ultrasónico cambia detalle en frecuencia por el detalle temporal que exige un pulso de ecolocación de 1–10 ms. Es el compromiso clásico de incertidumbre: no se pueden tener ambos, y qué lado conviene depende de qué se esté escuchando.

**Rasgos por marco** (todos a partir del espectro de magnitud `|X|`):

| Rasgo | Definición | Se lee como |
|---|---|---|
| Flujo espectral | $\Phi(t) = \sqrt{\sum_k \max(0,\,\lvert X(t,k)\rvert - \lvert X(t-1,k)\rvert)^2}$ | tasa de *cambio* espectral; rectificado de media onda para que solo cuente la energía nueva. **Es la señal de detección.** |
| Centroide espectral | $C(t) = \left(\sum_k f_k \lvert X \rvert\right) / \left(\sum_k \lvert X \rvert\right)$ | brillo, en Hz |
| Planitud espectral | $F(t) = \exp\left(\overline{\ln \lvert X \rvert^2}\right) / \overline{\lvert X \rvert^2}$ | 1.0 = ruido blanco, 0.0 = tono puro (entropía de Wiener) |
| Energía por banda | $E_b(t) = \sum_{f_k \in b} \lvert X(t,k)\rvert^2$ | potencia por banda ecológica |

Dos salvedades que importan para la interpretación y para cualquier modelo entrenado sobre esto: **el centroide y la planitud son ambos globales**, calculados sobre el espectro completo y no dentro de la banda propia del evento. Un evento de banda limitada reporta entonces una planitud que refleja cuánto llena del espectro *entero*, y un centroide empujado hacia arriba por el piso de ruido de banda ancha. Ver el ejemplo de la lluvia más arriba para los números medidos.

**Bandas ecológicas.** Semiabiertas `[lo, hi)` en Hz, recortadas a Nyquist para que una grabación de 48 kHz reporte energía cero por encima de 24 kHz en vez de inventarla.

| Banda | Rango | Contenido ecológico |
|------|-------|--------------------|
| `geophony` | 0–2 kHz | viento, lluvia, agua corriente, truenos lejanos |
| `biophony_low` | 2–4 kHz | anuros, mamíferos grandes, palomas y tinamúes |
| `biophony_mid` | 4–8 kHz | la mayor parte del canto de paseriformes, muchos ortópteros |
| `biophony_high` | 8–16 kHz | chicharras, esperanzas, paseriformes agudos |
| `ultrasonic` | 16–24 kHz | el borde grave de las llamadas de murciélago, si la frecuencia lo permite |

Con `--ultrasonic` la última banda se reemplaza por `ultrasonic_low` (16–40 kHz), `ultrasonic_mid` (40–80 kHz) y `ultrasonic_high` (80–160 kHz).

### Detección de eventos

Un evento es un momento en que el espectro *cambia*, medido contra lo que la grabación ha venido haciendo recientemente:

$$\Phi(t) > \mathrm{median}_{W}(\Phi) + \kappa \cdot 1.4826 \cdot \mathrm{MAD}_{W}(\Phi)$$

donde *W* es una **ventana causal de 60 segundos** (solo mira hacia atrás, de modo que la detección podría correr en vivo), κ es `--threshold` (2.5 por defecto), y 1.4826 es la constante que vuelve a la MAD un estimador consistente de la desviación estándar para datos normalmente distribuidos.

Mediana y MAD en lugar de media y σ porque una línea base robusta es justamente el punto: un único evento fuerte no debe elevar la vara que juzga a los eventos vecinos. El punto de ruptura de la MAD es del 50 %: la mitad de la ventana puede ser atípica antes de que la estimación se mueva.

1. Calcular la mediana y la MAD móviles de Φ sobre la ventana causal
2. Disparar donde Φ supere el umbral; los marcos contiguos forman una región
3. Fusionar regiones más cercanas que `--merge-gap` (5 s por defecto)
4. Descartar eventos fusionados más cortos que `--min-event-duration` (2 s por defecto)
5. Rellenar cada clip con margen previo/posterior, con tope en `--max-clip-duration`

Como la línea base se adapta continuamente, los fondos no estacionarios —la llegada de la lluvia, un coro del amanecer que se construye durante veinte minutos— elevan el umbral con ellos en lugar de saturar al detector.

**Los preajustes de sensibilidad** mueven κ y los tiempos a la vez:

| Preajuste | κ (unidades MAD) | Duración mín. | Brecha de fusión |
|---|---|---|---|
| `subtle` | 1.5 | 1.0 s | 3 s |
| `balanced` (por defecto) | 2.5 | 2.0 s | 5 s |
| `salient` | 4.0 | 3.0 s | 8 s |
| `dense` | 8.0 | 0.3 s | 0.25 s |

`dense` existe porque los tres primeros fallan en un paisaje sonoro
continuamente activo. κ se mide en desviaciones estándar robustas del flujo
*local*, así que se adapta al volumen, pero no a cuán incesantemente cambia un
paisaje sonoro. Ajustado sobre 2.1 horas de grabaciones de amanecer y atardecer
de Manakai a 192 kHz:

| Ajuste | eventos/h | mediana | p90 | cobertura |
|---|---|---|---|---|
| `balanced` (κ 2.5, fusión 1 s) | 24 | 7.4 s | **499 s** | **98 %** |
| `dense` (κ 8, fusión 0.25 s) | 619 | 0.9 s | 5.8 s | 46 % |

Una cobertura del 98 % significa que el detector solo está informando "aquí hay
sonido", y un evento de 499 segundos no cabe en el clip que debe contenerlo. En
una hora de amanecer, el mismo archivo da 12 eventos con mediana de 108 s y
máximo de 1780 s con `balanced`, frente a 548 eventos con mediana de 0.8 s y
máximo de 47 s con `dense`.

Nótese que κ está en **desviaciones estándar robustas del flujo local**, no en un nivel absoluto: el mismo ajuste se comporta de forma comparable en un sitio ruidoso y en uno silencioso, que es lo que hace significativa la comparación entre sitios.

### Clasificación desde la ecología profunda: el Parlamento de lo Viviente

Los eventos se catalogan por su **rol en el paisaje sonoro**, no por identidad de especie. Todos los participantes acústicos —biológicos, geológicos, humanos— se tratan como poseedores de valor ecológico intrínseco, y el sistema mide la democracia acústica como la entropía de Shannon de la distribución de roles.

**Voces biofónicas:** `dawn_chorus_participant`, `dusk_chorus_participant`, `nocturnal_voice`, `territorial_announcement`, `alarm_or_alert`, `insect_chorus`, `amphibian_assembly`, `bat_echolocation` (solo en modo ultrasónico)

**Elementos geofónicos:** `rain_event`, `wind_event`, `water_flow`

**Intrusiones antrofónicas:** `mechanical_intrusion`, `aircraft_passage`

**Transiciones acústicas (ecotonos temporales):** `silence_to_activity`, `activity_to_silence`, `community_shift`

La clasificación usa hora del día (de la marca temporal del AudioMoth), banda dominante, planitud espectral, duración y distribución de energía, y reporta una puntuación de confianza con un razonamiento legible.

### Índices ecoacústicos

Calculados por evento y por grabación:

| Índice | Referencia | Descripción |
|-------|-----------|-------------|
| **ACI** | Pieretti et al. 2011 | Variabilidad temporal dentro de cada banda de frecuencia. Alto = actividad biofónica compleja. |
| **BIO** | Boelman et al. 2007 | Área bajo la curva del espectro medio, 2–8 kHz. |
| **NDSI** | Kasten et al. 2012 | (biofonía − antrofonía) / total. −1 = toda antrofonía, +1 = toda biofonía. |
| **ADI** | Villanueva-Rivera et al. 2011 | Entropía de Shannon de las proporciones de actividad por banda. |
| **AEI** | Villanueva-Rivera et al. 2011 | Coeficiente de Gini de la actividad por banda. |

Los cinco se calculan dos veces: una por evento (solo sobre los marcos de ese evento) y otra por grabación completa. Los valores por evento son los que quedan en `events.json` y en las leyendas del video; los valores por grabación alimentan el calendario.

Estadísticos del parlamento por grabación, ambos entropías de Shannon sobre el conjunto de eventos:

$$H = -\sum_i p_i \log_2 p_i$$

- **Índice de democracia** — *p* sobre la distribución de **roles** ecológicos. Más alto significa que ningún tipo de voz domina el ensamblaje.
- **Partición de nicho** — *p* sobre la distribución de **bandas** dominantes. Más alto significa que la comunidad se reparte por el espectro en vez de agolparse en una banda.

Ambos heredan la calibración del clasificador: el índice de democracia solo es tan significativo como la asignación de roles que lo sostiene, mientras que la partición de nicho descansa sobre energías por banda y es, por tanto, el más sólido de los dos.

---

## Fases fenológicas y su relación con los colores

La capa del calendario es donde se encuentran color, clasificación y temporada. Cada día de grabación se reduce a un marco de escalares; una fase es un **cambio sostenido en la composición de esos marcos**, no una propiedad que tenga ningún clip individual.

### De los clips a las fases

```
clips de evento (coloreados por dominio)
  → agregación diaria     conteos de roles, proporciones de dominio, energías, índices medios
  → marco por día         actividad, riqueza, proporciones de biofonía/geofonía/antrofonía…
  → normalización         cada campo también escalado a 0-1 sobre el conjunto (cv)
  → detección de fases    comparaciones día a día que cruzan un umbral
```

Las proporciones de dominio en el marco de cada día son literalmente *la proporción de los clips de ese día renderizados en cada color*. Una galería cuyas tarjetas pasan de verde a azul en quince días es el mismo hecho que `cv_geophony` subiendo y `cv_biophony` bajando, y el mismo hecho que un evento `rain_season_transition` en el calendario. Color, columna del CSV y mensaje OSC son tres representaciones de una sola medición.

### Los cinco detectores de fase

| Fase | Se dispara cuando | Lee de | Umbral |
|---|---|---|---|
| `breeding_chorus_onset` | la energía de `biophony_low` **y** `biophony_high` más que se duplica frente al día anterior | energías por banda | `breeding_energy_ratio` = 2.0 |
| `migration_acoustic_shift` | el ADI cambia más de 0.5 entre días — nichos de frecuencia que se abren o cierran | ADI medio | `adi_shift` = 0.5 |
| `rain_season_transition` | el conteo de eventos geofónicos salta en más de 3 en un día | conteos de dominio | `geophony_event_jump` = 3 |
| `dawn_chorus_advance_delay` | el primer evento biofónico de la mañana se desplaza más de 15 min | horas de inicio del coro | `dawn_shift_minutes` = 15 |
| `nocturnal_community_change` | el conjunto de roles activos de noche gana o pierde un miembro | conjuntos de roles | cualquier cambio |

Por qué estas cinco: son las señales fenológicas que un **paisaje sonoro** puede transportar sin identificación de especies. Los coros reproductivos son una fase reproductiva (anuros en la banda baja, ortópteros en la alta — de ahí que se exija que ambas se muevan juntas, lo que distingue un coro de una fuente de ruido de paso). El horario del coro del amanecer sigue al fotoperiodo y es uno de los relojes estacionales más confiables en el trópico, donde las señales de temperatura son débiles. En un **bosque seco tropical** en particular, la transición seca–lluvias es el evento anual dominante, y se anuncia por partida doble: directamente como geofonía, e indirectamente como la explosión de anuros que sigue a las primeras lluvias en cuestión de días.

El inicio del amanecer merece una salvedad: hoy se define como el primer evento biofónico entre las 03:00 y las 08:00, lo que depende de que exista efectivamente una grabación a esa hora. Los huecos de un ciclo de trabajo se convierten en "retrasos" espurios. Para fenología, programe grabaciones que cubran el amanecer todos los días en lugar de muestrear de manera oportunista.

### El color de una temporada

Como el mapa de color lo elige el dominio, una temporada tiene una firma visual que se lee directamente en la galería o en el mapa de calor del calendario:

- **Temporada seca, amanecer** — mayormente verde, concentrado en `biophony_mid`, con `democracy_index` alto porque se solapan muchas especies de aves
- **Primeras lluvias** — aparecen transiciones magma cuando cambian los regímenes, y luego bloques azules de geofonía
- **Temporada de lluvias, noche** — verde otra vez pero desplazado hacia lo grave (`biophony_low`, coro de anuros) y lo agudo (`biophony_high`, ortópteros), con el medio más vacío; `niche_partitioning` sube
- **Cualquier temporada, cerca de una vía** — bandas ígneas que reaparecen en horarios humanos, y `NDSI` cayendo hacia cero o por debajo

Esos son los patrones que los índices están diseñados para cuantificar, y la razón por la que se conservan tanto el color como el número de cada evento.

---

## Usar esto como conjunto de datos (aprendizaje automático)

El pipeline es un **front end de etiquetado débil y segmentación**, no un clasificador en el que se pueda confiar como verdad de referencia. Lea esta sección antes de entrenar cualquier cosa con su salida.

### Para qué sirve cada artefacto

| Artefacto | Sirve como | No sirve como |
|---|---|---|
| `clips/**/*.wav` | audio de entrenamiento, ya segmentado por evento con contexto | — |
| `onset_s`, `offset_s`, `duration_s` | objetivos de segmentación; derivados de la señal, no de un juicio | fronteras precisas (cruces de umbral, ±1 marco) |
| `band_energies`, `centroid`, `flatness`, `peak_flux` | rasgos de entrada; funciones deterministas del audio | — |
| `aci`, `bio`, `ndsi`, `adi`, `aei` | rasgos de entrada; publicados y comparables entre estudios | — |
| `dominant_band` | una etiqueta gruesa confiable — es solo un argmax sobre energía medida | identidad de especie |
| `domain` | una etiqueta débil defendible de 4 clases | verdad de referencia donde dominan las transiciones |
| `role` | una **hipótesis** de umbrales ajustados a mano | objetivo de entrenamiento sin verificación humana |
| `confidence` | una constante asignada a mano por rama de regla | una probabilidad calibrada |
| `certainty` | un nivel de triaje — qué roles merecen tiempo humano | evidencia en sí misma |

Esa última fila importa: `confidence` no se aprende ni se estima. Cada regla devuelve un número fijo que el autor le asignó (0.8 para una coincidencia de coro del amanecer, 0.3 para un respaldo). Ordena las reglas según cuán específicas son, nada más.

### Esquema de `events.json`

Un archivo por grabación, con rutas de medios relativas al directorio de ese archivo.

```jsonc
{
  "filename": "20250310_053000.WAV",
  "recording_datetime": "2025-03-10T05:30:00",   // null si no se puede interpretar
  "duration_s": 100.0,
  "sample_rate": 48000,
  "habitat": "Lagunas, lagos y ciénagas naturales",  // del nombre del directorio
  "season": "Época lluvias",
  "temperature_c": 24.5,                          // cabecera AudioMoth, puede ser null
  "indices":   { "aci": …, "bio": …, "ndsi": …, "adi": …, "aei": … },  // grabación completa
  "band_energies": { "geophony": …, "biophony_low": … },               // media por evento
  "parliament": { "total_voices": …, "domain_percentages": {…},
                  "role_counts": {…}, "democracy_index": …,
                  "niche_partitioning": … },
  "n_events": 6,
  "n_clips": 6,
  "events": [{
    "event_index": 3,
    "onset_s": 40.8, "offset_s": 45.8, "duration_s": 5.0,
    "clip_start_s": 20.8, "clip_end_s": 55.8,   // incluye margen previo/posterior
    "peak_flux": …, "mean_flux": …,
    "centroid": 5412.0,        // Hz, ponderado por magnitud, espectro completo
    "flatness": 0.081,         // 0-1, espectro completo
    "band_energies": { … },    // por banda, solo los marcos de este evento
    "band_crest": 35.1,        // pico/media dentro de la banda — ver docs/CALIBRACION.md
    "band_entropy": 0.27,      // dispersión dentro de la banda, 0-1
    "band_centroid": 1240.0,   // Hz, solo dentro de la banda dominante
    "periodicity": 0.47,       // modulación dentro del evento, 0-1
    "pulse_rate_hz": 15.6,
    "context_periodicity": 0.06,  // modulación en una ventana de 4s alrededor
    "context_rate_hz": 1.2,       // REGISTRADO PERO AÚN NO USADO PARA CLASIFICAR
    "role": "dawn_chorus_participant",
    "domain": "biophony",
    "confidence": 0.8,         // fijo por regla — ver la salvedad arriba
    "dominant_band": "biophony_mid",
    "reasoning": "Mid-frequency activity during dawn hours (h=5)",
    "aci": …, "bio": …, "ndsi": …, "adi": …, "aei": …,
    "clip_path": "clips/biophony/dawn_chorus_participant/event_003_….wav",
    "video_path": "…mp4", "poster_path": "…png",
    "thumbnail_path": "…png", "gif_path": ""
  }]
}
```

`phenological_series.csv` trae una fila por día: los campos crudos y luego copias `cv_*` de cada uno escaladas a 0–1 sobre el conjunto. `phenological_calendar.json` guarda los mismos marcos más las fases detectadas y los rangos de normalización usados.

### Sesgos conocidos que hay que tener en cuenta

1. **La detección responde al cambio, no a la presencia.** Una chicharra que canta continuamente durante una hora produce un evento al inicio y nada después. La ausencia de eventos no es ausencia de sonido: es ausencia de *cambio*. Cualquier modelo entrenado con estos clips hereda un sesgo de muestreo hacia inicios y transiciones.
2. **Las reglas de transición tienen prioridad sobre las de contenido.** El primer evento de un régimen nuevo se etiqueta `silence_to_activity` o `activity_to_silence` sin importar la fuente. En el corpus de verificación eso se tragó la mayoría de los inicios de lluvia.
3. **Algunos roles nunca se disparan con los umbrales actuales.** `rain_event`, `wind_event`, `water_flow`, `mechanical_intrusion` y `aircraft_passage` se emitieron cero veces en 45 eventos, por las razones de los rasgos documentadas antes. No lea un conteo en cero como ausencia de lluvia.
4. **Las reglas dieles dependen de un reloj correcto.** Los roles anclados a la hora del día valen lo que valga la marca temporal del AudioMoth, y una zona horaria equivocada reetiqueta en silencio un coro del amanecer como nocturno.
5. **El desbalance de clases es severo y específico del sitio.** 11 de 45 eventos del corpus de prueba correspondieron a un solo rol.
6. **El ultrasonido está ausente si no se pide.** Cualquier cosa entrenada con la salida por defecto nunca ha visto un murciélago.

### Un camino razonable hacia un modelo entrenado

1. Correr la detección con `--sensitivity subtle` para sobre-segmentar: es mejor descartar que perder.
2. Usar `dominant_band` y los rasgos numéricos como la capa confiable; tratar `role` como un preordenamiento para anotar, no como etiqueta.
3. Que una persona verifique los clips en el orden de la galería: agrupar por rol hace que quien anota confirme o rechace una hipótesis a la vez, mucho más rápido que etiquetar desde cero.
4. Calibrar los umbrales del inicio de `classifier.py` contra esas etiquetas verificadas; volver a correr la detección es barato frente a volver a anotar.
5. Conservar el CSV fenológico como **señal de validación reservada**: un modelo que no puede reproducir una transición seca–lluvias conocida no está modelando el sitio.

El protocolo completo está en [docs/CALIBRACION.md](docs/CALIBRACION.md).

---

## Estructura del paquete

```
bioacoustics.sh          Punto de entrada único — asistente, o cualquier subcomando
detect_events.sh         Acceso directo al pipeline de detección

bioacoustic_detector/
  wizard.py              Interfaz guiada a todas las funciones
  cli.py                 Subcomandos y análisis de argumentos
  pipeline.py            La cadena de etapas, por archivo y por lote
  config.py              Todos los parámetros ajustables y los preajustes
  spectral.py            STFT, flujo, centroide, planitud, energías por banda
  detector.py            Detección de eventos por umbral adaptativo
  classifier.py          Taxonomía desde la ecología profunda
  indices.py             ACI, BIO, NDSI, ADI, AEI
  clipper.py             Extracción de clips, filtros y archivado por rol
  video.py               Videos por clip, fijas, GIFs, reels por tipo
  media.py               Plomería de ffmpeg; partir video y convertir a GIF
  gallery.py             Galería de clips con lightbox y etiquetado GPS
  phenology.py           Calendario, marcos OSC, CSV, HTML
  osc_output.py          Mensajes OSC, paquetes, partituras SuperCollider, streaming
  osc_server.py          Servidor OSC bidireccional de consultas
  metadata.py            Metadatos AudioMoth; cobertura/época desde las rutas
  report.py              Reportes HTML por grabación y por lote
  store.py               Lectura/escritura de events.json con rutas portables
```

---

## Requisitos

- **Python 3.10 o superior.** macOS trae 3.9 como `/usr/bin/python3`; el lanzador busca un intérprete más nuevo y reconstruye su entorno virtual si encuentra uno más viejo. Instálelo con `brew install python@3.12` si hace falta.
- **ffmpeg** — opcional, pero necesario para video de espectrograma, imágenes fijas y GIFs. Sin él igual se obtienen clips, `events.json`, exportaciones OSC, el calendario y los reportes; el pipeline lo dice y continúa. `brew install ffmpeg`.
- **Un ffmpeg con `drawtext`**, si quiere leyendas incrustadas en los videos. El paquete estándar de Homebrew se compila sin libfreetype y por tanto no tiene el filtro `drawtext`, así que las leyendas quedan silenciosamente indisponibles — el espectrograma, la leyenda de ejes, los colores y el audio no se ven afectados. `brew install ffmpeg-full` lo provee; la herramienta prefiere esa compilación automáticamente, o defina `FFMPEG_BIN=/ruta/a/ffmpeg` para elegir la suya.
- Paquetes de Python (instalados automáticamente en el entorno gestionado): `numpy`, `scipy`, `soundfile`, `metamoth`, `python-osc`.
- **Opcional:** `alp-data` (Python 3.11+), solo para `./bioacoustics.sh validate`. Ningún otro módulo lo importa, y el comando indica cómo instalarlo si falta.

`./bioacoustics.sh doctor` informa sobre todo lo anterior.

---

## Solución de problemas

**"Python 3.10 or newer is required but was not found."**
Instale un intérprete más nuevo (`brew install python@3.12`) y vuelva a ejecutar. El lanzador busca desde `python3.14` hasta `python3.10`, luego `python3`, y también revisa `/opt/homebrew/bin` y `/usr/local/bin` por si Homebrew no está en su `PATH`. No usará el 3.9 del sistema de macOS.

**Los videos se renderizan pero no traen leyenda.**
Su ffmpeg no tiene el filtro `drawtext`: se compiló sin libfreetype, que es el caso del paquete estándar actual de Homebrew. `./bioacoustics.sh doctor` muestra qué filtros trae su compilación. El rol, la confianza, la banda, la cobertura y la fecha del clip siguen estando en el nombre del archivo, en la tarjeta de la galería, en el reporte y en `events.json`; lo único que falta es el texto incrustado. Para obtenerlo:

```bash
brew install ffmpeg-full     # keg-only; la herramienta lo encuentra y lo prefiere
# o
export FFMPEG_BIN=/ruta/a/un/ffmpeg-con-drawtext
```

**No apareció ningún video de espectrograma.**
Falta ffmpeg: la corrida lo advierte sobre la marcha y produce todo lo demás. Instálelo y vuelva a correr `detect` sobre la misma entrada: los medios se renderizan durante la detección, así que no hay un paso de renderizado aparte que retomar. Los clips y el JSON de la primera pasada simplemente se sobrescriben.

**"No WAV files found in: …"**
La ruta se evalúa tal como se escribe, relativa a donde usted está parado (no al repositorio). Entrecomille rutas con espacios o tildes: `./detect_events.sh "Epoca lluvias/Bosque de galería y-o ripario/"`. Se encuentran tanto `.WAV` como `.wav`, de forma recursiva.

**Demasiados o muy pocos eventos.**
Empiece con `--sensitivity subtle | balanced | salient`, y recurra a `--threshold` (unidades MAD — más bajo es más sensible) solo si los preajustes no dan en el punto. `--min-event-duration` descarta destellos breves; `--merge-gap` decide qué tan separados deben estar dos disparos para contar como eventos distintos. Explore primero con `--json-only`: el mismo análisis, sin nada del renderizado. Ver [Detección de eventos](#detección-de-eventos) para qué mide κ realmente.

**"Only one recording — the calendar needs several to compare."**
La fenología es un producto entre grabaciones. Necesita grabaciones de al menos dos días distintos, cada una con una marca temporal interpretable: un nombre AudioMoth `YYYYMMDD_HHMMSS.WAV` o metadatos AudioMoth intactos. La corrida informa cuántos de sus archivos tienen marcas temporales utilizables.

**No llega nada al instrumento.**
Verifique el destino con `--host` y `--port` (por defecto `127.0.0.1:57120`, el de SuperCollider). `osc serve` escucha en `--listen-port` (57121 por defecto) y *responde* a `--host`/`--port`, que puede redirigirse en tiempo de ejecución enviando `/phenology/query/reply_port <int>`. Haga `cat osc_address_map.txt` para ver las direcciones exactas que emiten sus resultados.

**Un enlace de la galería no abre nada.**
Las rutas de medios dentro de `events.json` se guardan relativas a la carpeta de cada grabación, de modo que todo el árbol de salida puede moverse o publicarse como una unidad — pero mover `gallery.html` por separado rompe sus enlaces. Regenérela en su sitio con `./bioacoustics.sh gallery <carpeta_de_salida>`.

**Un script viejo imprimió una nota sobre un comando nuevo.**
Es lo esperado. Los siete scripts retirados siguen funcionando; reenvían al pipeline y nombran su reemplazo. Ver [Scripts reemplazados](#scripts-reemplazados).
