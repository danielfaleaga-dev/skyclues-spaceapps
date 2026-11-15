# Instrucciones para agentes que trabajen en SkyClues

Antes de cambiar código, leer `PROJECT_CONTEXT.md` y la primera sección de `PROJECT_STATE.md`.

**Antes de cualquier cambio visible** —texto, controles, paneles, gráficas, carga, HTML/CSS o comportamiento de navegación— **leer `DESIGN_SYSTEM.md` completo**. Sus decisiones forman parte del encargo del usuario, no son sugerencias opcionales. Aplican también a nuevas funciones y a los componentes embebidos/iframes. Las instrucciones nuevas del usuario prevalecen.

- Continuar la interfaz unificada de esta rama. No reconstruir otra interfaz ni recuperar un diseño antiguo.
- Usar los componentes y estilos compartidos; no introducir estilos aislados que rompan la paleta, tipografía o jerarquía.
- Mantener dos niveles de presentación: Sencillo para explorar; Científico para métodos, parámetros y rigor. Cambiar de nivel no cambia datos, parámetros activos ni resultados.
- Mantener un único estado de región y distinguir catálogo, predicción y observación.
- No cambiar motores científicos ni máscaras para resolver problemas visuales.
- Comprobar en navegador la zona afectada en ambos niveles y, si cambia la disposición, en una ventana estrecha. Validar interacción, estados de carga/error/vacío y conservación del FOV cuando corresponda.
- Actualizar `DESIGN_SYSTEM.md` si el usuario aprueba una decisión visual nueva y `PROJECT_STATE.md` al terminar. Documentar qué se comprobó realmente.
- Conservar respaldos y cambios existentes. Crear commits locales está autorizado; push, publicación, despliegue o envío a NASA requieren autorización explícita del usuario.

No se establece una obligación de pedir confirmación para ajustes reversibles dentro de este diseño. No delegar en otros agentes salvo petición explícita del usuario.
