# Hallazgos del censo de `textures/` — Skyrim SE (32.241 DDS, 18,2 GB)

Formato fijo: `AFIRMACIÓN — CONSULTA QUE LA PRODUJO — N — EXCEPCIONES ENCONTRADAS`.
Sin recomendaciones. Sin "se suele". Si no hay consulta detrás, no está acá.

---

### 1. Validación del parser

**AFIRMACIÓN**: El parser predice el tamaño exacto en bytes de **32.241 de
32.241** archivos, desde formato + dimensiones + mipmaps + caras + profundidad.
0 fallos, 0 ilegibles.
**CONSULTA**: `python census/parser_dds.py --autotest textures`
**N**: 32.241
**EXCEPCIONES**: ninguna. Dos huecos del parser se descubrieron **por esta
misma identidad** y se cerraron: 59 cubemaps (guardan 6 caras) y 1 textura de
volumen (`effects/noisevolume.dds`, guarda una pila de slices). Los dos
cerraron al byte tras la corrección, no por aproximación.

> Esta suite es más fuerte que valores esperados a mano: la relación
> `bytes = cabecera + Σ ceil(w/4)·ceil(h/4)·bpb · caras · profundidad`
> la impone el formato, así que cada archivo del corpus es su propio caso de
> prueba. Ningún error de offset la sobrevive.

### 2. (a) Formato

**AFIRMACIÓN**: DXT5 55,2% (17.798); sin comprimir 32bpp 31,2% (10.048);
DXT1 13,0% (4.206); sin comprimir 24bpp 0,6% (188); sin comprimir 8bpp 1.
**BC7: 0 archivos.**
**CONSULTA**: conteo de `formato` sobre el censo
**N**: 32.241
**EXCEPCIONES**: 0 de 32.241 usan BC7, BC5, BC4 ni BC6H. El juego base es
DXT recomprimido de LE, no BC7. BC7 es lo que SE *admite*, no lo que Bethesda
*usó*.

### 3. (b) Los "sin comprimir" no son descuido

**AFIRMACIÓN**: De los 10.237 sin comprimir, 9.365 son de `terrain/`
(mapas de mezcla y LOD), 641 de `water/` y 212 de `actors/` — y estos últimos
son `_msn.dds`, normales en **espacio de modelo** de cabezas, que necesitan
precisión que un formato de bloques destruye.
**CONSULTA**: `formato contiene "sin_comprimir"`, agrupado por clase y sufijo
**N**: 10.237
**EXCEPCIONES**: 6 en `effects/`, 11 en `dlc01/`.

### 4. (c) Potencia de dos: invariante confirmado

**AFIRMACIÓN**: **0 de 32.241** texturas tienen un lado que no sea potencia de
dos.
**CONSULTA**: `not potencia_de_dos`
**N**: 32.241
**EXCEPCIONES**: 0 de 32.241. Sin excepciones en todo el corpus.

### 5. (c) Las cadenas de mipmaps cortan en 2×2

**AFIRMACIÓN**: El 96,4% (31.083) de las texturas termina su cadena de mipmaps
en **2×2**, no en 1×1. Solo 109 bajan hasta 1×1.
**CONSULTA**: nivel más chico alcanzado tras `mipmaps-1` reducciones
**N**: 32.241
**EXCEPCIONES**: 331 cortan en 4×2 y 309 en 2×4 (texturas no cuadradas);
190 no bajan de 512×512 (son las que directamente no tienen mipmaps).

> Una primera versión de esta consulta medía "cadena completa" contra 1×1 y
> reportaba **31.940 texturas rotas**. Eran correctas: la métrica estaba mal
> definida. Un número que acusa al 99% del corpus es sospechoso del medidor,
> no del medido.

### 6. (c) Sin mipmaps

**AFIRMACIÓN**: 192 de 32.241 (0,6%) no tienen mipmaps. 188 están en
`actors/character/character assets/` (máscaras de tinte) y 4 en `effects/`
(reflejo y lens flares).
**CONSULTA**: `sin_mipmaps == True`, agrupado por carpeta
**N**: 32.241
**EXCEPCIONES**: ninguna fuera de esas dos familias. Ninguna es una textura de
superficie que se vea a distancia.

### 7. (d) Sufijo × formato: la convención real

**AFIRMACIÓN**: `_n` (normal map) usa **DXT5 en el 100%** de 12.075 archivos.
Los demás sufijos se reparten: `_d` DXT1 57% / DXT5 42%; `_m` DXT5 64% /
DXT1 36%; `_g` DXT1 64%; `_s` DXT1 100% (N=29).
**CONSULTA**: sufijo del nombre × `formato`
**N**: 32.241 (19.108 sin sufijo reconocible)
**EXCEPCIONES**: **0 de 12.075** normales usan algo distinto de DXT5. Es el
patrón más limpio del corpus.

### 8. (e) Resolución

**AFIRMACIÓN**: 66,9% son 256×256 (21.557); 14,7% 512×512; 7,1% 1024²;
5,2% 2048². Solo **57 archivos (0,18%)** llegan a 4096 o más.
Mediana del lado mayor por clase: `terrain` 256, `actors` 512, `clutter` 512,
`architecture` 1024, `armor` 1024.
**CONSULTA**: conteo de `ancho x alto`; mediana de `max(ancho, alto)` por clase
**N**: 32.241
**EXCEPCIONES**: el máximo del corpus es **8192**, en `architecture/`.

### 9. (g) Peso

**AFIRMACIÓN**: 18,2 GB. DXT5 se lleva 11,45 GB (63%), sin comprimir 32bpp
4,08 GB (22%), DXT1 2,52 GB (14%).
**CONSULTA**: suma de `bytes` por formato
**N**: 32.241
**EXCEPCIONES**: ninguna.

### 10. (f) Cubemaps y volúmenes

**AFIRMACIÓN**: 58 cubemaps y **1** textura de volumen en todo el corpus.
**CONSULTA**: `cubemap == True`, `volumen == True`
**N**: 32.241
**EXCEPCIONES**: el único volumen es `effects/noisevolume.dds`, 128×128×128.

---

## Lo que este censo NO mide

- **Contenido de píxeles.** No se decodifica nada: solo encabezados. Si el
  albedo trae luz horneada, si el canal alfa de un normal está en negro, o si
  la máscara `_m` tiene rango comprimido, este censo **no lo sabe**.
- **UV.** El solape de islas, la densidad de téxel y el desperdicio de atlas
  necesitan la malla y la textura juntas. No está hecho.
- **Resolución de rutas.** El cruce NIF→archivo se hizo a mano una vez (393 de
  10.008 rutas sin resolver, de las cuales solo 6 malformadas) pero no está
  automatizado acá.
