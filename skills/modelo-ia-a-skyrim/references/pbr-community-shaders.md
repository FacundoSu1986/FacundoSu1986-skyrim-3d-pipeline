# True PBR de Community Shaders

Community Shaders es un mod SKSE que reemplaza los shaders de Skyrim SE. Su
**True PBR** dibuja una malla con materiales PBR de verdad (rugosidad,
metalicidad, reflectancia) en vez de la máscara especular y el cubemap de
vanilla. Es una rama **aparte** de la capa HD (`hd-texturas.md`): otro juego
de texturas y otras flags en el NIF. No se mezcla con el `_n` vanilla en la
misma pieza.

Todo lo de esta página es `[PROVIDER]`: depende de un mod de terceros y caduca
cuando él cambia. No sale de la memoria ni de guías de foro. Sale de su
**código fuente**, fijado a un commit:

| Fuente | Qué se leyó |
|---|---|
| `community-shaders/skyrim-community-shaders`, commit `898b167` (GPL-3.0) | `src/TruePBR.cpp`, `src/TruePBR/BSLightingShaderMaterialPBR.{h,cpp}`, `package/Shaders/Lighting.hlsl` |
| CommonLibVR `70c1acd` (el submódulo que usa ese commit) | `BSShaderProperty.h`: los bits de las flags |
| `ThePagi/PBRNifPatcher` (GPL-3.0) | `NifPatcher2.cpp` y su README: qué escribe en el NIF una herramienta que la comunidad usa |

Si una versión nueva de Community Shaders cambia algo de esto, manda el código
nuevo, no esta página.

**Lo que NO se probó:** nada de esto se vio en el juego con Community Shaders
instalado. Tampoco se probó cómo se ve un NIF marcado como PBR **sin**
Community Shaders. Lo medido está marcado como tal.

## Qué prende el PBR en el NIF

| Qué | Valor | De dónde |
|---|---|---|
| Flag | `Shader_Flags_2`, **bit 23** | CS: `kMenuScreen` = bit 55 de las 64 (32 + 23). NifSkope lo muestra como `Unused01`; PyNifly, `ShaderFlags2.UNUSED01`; nifly, `SLSF2_UNUSED01 = 1 << 23` |
| Tipo de shader | `Default` (0); `MultiLayer` (11) para la capa | PBRNifPatcher vuelve a `Default` y apaga EnvMap, Parallax, Glow_Map, Back_Lighting y Multi_Layer_Parallax |

`[MEASURED]` **0 de 74.489** `BSLightingShaderProperty` vanilla tienen ese bit
(leídos con `material_arma.py` sobre 22.393 NIF). Un NIF vanilla nunca se
confunde con uno PBR.

Con el PBR prendido, CS reinterpreta otras flags de `Shader_Flags_2`
(`TruePBR.cpp`):

| Flag | Bit de flags2 | Con PBR |
|---|---|---|
| `Rim_Lighting` | 26 | subsurface |
| `Soft_Lighting` | 25 | fuzz (tela, terciopelo) |
| `Back_Lighting` | 27 | pelo (Marschner) |
| `Multi_Layer_Parallax` | 24 | dos capas (coat); ahí `Soft_Lighting` = parallax entre capas, `Back_Lighting` = normal de la capa, `Effect_Lighting` (30) = capa con color |
| `Fit_Slope` | 12 | destellos (glints), si no hay fuzz |

Y apaga internamente `Specular`, `Glow_Map`, `Environment_Mapping` y las
demás de iluminación vanilla: el especular sale del `_rmaos`.

## Los campos del NIF cambian de significado

| Campo del NIF | Vanilla | Con PBR | De dónde |
|---|---|---|---|
| `Glossiness` | brillo (mediana 80 en armas) | **nivel especular** de lo no metálico (F0); CS usa 0,04 por defecto | `GetSpecularLevel()` = `specularPower`; PBRNifPatcher escribe `specular_level` con `SetGlossiness` |
| `Specular Strength` | intensidad especular | **escala de rugosidad**: multiplica el R del `_rmaos` | `GetRoughnessScale()` = `specularColorScale`; PBRNifPatcher: `SetSpecularStrength(roughness_scale)` |
| `Lighting Effect 2` (rim) | potencia de la luz de borde | escala del desplazamiento (`_p`) | `GetDisplacementScale()` = `rimLightPower`; PBRNifPatcher: `rimlightPower = displacement_scale` |
| `Specular Color` | color especular | color del subsurface o de la capa | `GetSubsurfaceColor()` = `specularColor` |

**La trampa:** un NIF armado para vanilla con glossiness 80, o salido de
PyNifly con 20 sin fijar (trampa 36), queda con un nivel especular de 80 o 20
cuando lo esperable es 0,04. `material_arma.py` lo avisa.

## Las ranuras del texture set

`BSLightingShaderMaterialPBR.h` define las ranuras y dice qué va en cada
canal. Los sufijos son la convención de PBRNifPatcher, que sigue la de
Skyrim.

| Ranura | Vanilla | True PBR | Sufijo | Canales |
|---|---|---|---|---|
| 0 | color | color base | `x.dds` | RGB albedo (sRGB) |
| 1 | `_n` | normal | `x_n.dds` | RGB normal, mismo verde OpenGL que vanilla |
| 2 | glow | emisivo | `x_g.dds` | RGB color de emisión. Se activa con tener textura |
| 3 | parallax | desplazamiento | `x_p.dds` | R altura. Se activa con tener textura |
| 4 | cubemap | — | — | no se usa |
| 5 | `_m` (máscara de reflejo) | **RMAOS** | `x_rmaos.dds` | R rugosidad, G metalicidad, B oclusión, A reflectancia de lo no metálico |
| 6 | — | fuzz / normal de la capa | `x_cnr.dds` | fuzz: RGB color, A peso. Capa: RGB normal, A rugosidad |
| 7 | — | subsurface / color de la capa | `x_s.dds` | RGB color, A espesor o fuerza |

Tres detalles del código:

- **La ranura 5 vacía no es neutra.** CS carga ahí una textura blanca:
  rugosidad 1 y metal 1 en toda la pieza. Si además falta el difuso o el
  normal, escribe `missing ...; treating as nonPBR` en su log y dibuja la
  pieza sin PBR.
- **El alfa del `_rmaos` multiplica el nivel especular del NIF**
  (`rawRMAOS *= float4(PBRParams1.x, 1, 1, PBRParams1.z)` en
  `Lighting.hlsl`). En 255 deja el `Glossiness` tal cual. La wiki de CS
  sugiere BC1, sin alfa, cuando no se usa.
- **El alfa del `_n` no entra en el material PBR.** Solo la ruta no diferida
  lo lee como glossiness para los reflejos en pantalla (SSR); la diferida usa
  `1 − rugosidad`. Por eso `255 − rugosidad`, lo que escribe la fase de
  texturas, es coherente en los dos casos.

PBRNifPatcher pone las texturas PBR bajo `textures\pbr\...` para no pisar las
vanilla con el mismo nombre. Es una convención, no un requisito de CS.

## Cuándo hace falta un JSON

`Data\PBRTextureSets\<EditorID>.json` da los parámetros de un registro TXST (y
del terreno), buscándolo por su EditorID. `Data\PBRMaterialObjects\` es lo
mismo para los material objects. Los campos del texture set son
`roughnessScale`, `displacementScale`, `specularLevel`, `subsurfaceColor`,
`subsurfaceOpacity`, `coatColor`, `coatStrength`, `coatRoughness`,
`coatSpecularLevel`, `innerLayerDisplacementOffset`, `fuzzColor`, `fuzzWeight`
y `glintParameters`.

Un arma o un objeto nuevo con las texturas escritas en su propio NIF **no
necesita JSON**: los parámetros salen de los campos del NIF, con la tabla de
arriba.

## Con este repo

1. **Hornear** con `scripts/hornear.py` (`hd-texturas.md`). Deja
   `_albedo`, `_normalgl`, `_roughness`, `_metallic` y `_ao`.
2. **Convertir** con la fase de texturas del pipeline y
   `sombreado="cs_pbr"` en el manifest. Escribe:
   - el color,
   - el `_n` con `255 − rugosidad` en el alfa,
   - el `_rmaos`: R rugosidad, G metal (0 si no hay), B oclusión (de un
     `_ao`, o del rojo de un `_orm`/`_arm`; 255 si no hay), A 255,
   - el `_g` si hay emisión y el `_p` si hay altura,
   - **no** escribe `_m`: en PBR la ranura 5 es del `_rmaos`.

   Sin fuente de rugosidad la fase falla: sin `_rmaos` quedaría el blanco.
   `texture_set.json` lleva las ranuras y los valores del NIF para la
   exportación.
3. **Exportar** el NIF con esos valores. Con PyNifly:

   ```python
   from pyn.nifconstants import BSLSPShaderType, ShaderFlags2

   p = sh.shader.properties
   p.Shader_Type = BSLSPShaderType.Default
   p.shaderflags2_set(ShaderFlags2.UNUSED01)      # el bit 23: prende el PBR
   p.Glossiness = 0.04                             # nivel especular, no brillo
   p.Spec_Str = 1.0                                # escala de rugosidad
   sh.set_texture('Diffuse', r'textures\pbr\weapons\x\x.dds')
   sh.set_texture('Normal', r'textures\pbr\weapons\x\x_n.dds')
   sh.set_texture('EnvMask', r'textures\pbr\weapons\x\x_rmaos.dds')  # ranura 5
   sh.save_shader_attributes()
   ```

   `[MEASURED]` Escrito con PyNifly y leído con `material_arma.py`: flags2 =
   `0x00808001` (bit 23 prendido), tipo Default, glossiness 0,04, el `_rmaos`
   en la ranura 5.
4. **Verificar** con `scripts/material_arma.py <nuevo.nif>`: reconoce la
   pieza PBR, no la compara con la tabla vanilla y avisa si falta el `_rmaos`,
   si la glossiness quedó en un valor vanilla o si el tipo de shader no es
   Default ni MultiLayer. Con EnvMap, el material PBR ni siquiera lee el
   campo extra de la escala del reflejo.

## Qué sigue abierto

- **Juego.** Nada de esto se vio con Community Shaders instalado.
- **Sin Community Shaders.** No se sabe cómo dibuja el juego vanilla un NIF
  con el bit 23 prendido. Si el mod tiene que funcionar para todos, hace falta
  una versión vanilla aparte, o el camino de PBRNifPatcher: se envían las
  texturas y un JSON de configuración, y cada usuario parchea sus NIF.
- **Compresión del `_rmaos`.** Con `compresion="dxt"` sale en DXT1, porque
  su alfa es 255 en todos lados. DXT1 comprime los tres canales juntos, y la
  rugosidad, el metal y la oclusión no tienen por qué parecerse: medido sobre
  los mapas horneados de `hd-texturas.md`, un error RMS de 3,5, 3,2 y 2,3
  niveles (de 255). Cuánto se nota, en el juego, no se midió. BC7, que
  comprime mejor esos canales, el repo no lo escribe.
- **Subsurface, capa, fuzz y glints.** Están documentados arriba desde el
  código, pero la fase no los arma.
