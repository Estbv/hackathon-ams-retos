# Reto 2: "El guardia que nunca se duerme"

### Agentes que vigilan un servicio, detectan la falla, investigan la causa y la reportan solos

---

## 1. Resumen del reto

Construyan un sistema de agentes basado en **Huawei Cloud MaaS** que se conecte a un servicio en producción y lo vigile sin supervisión. Cuando el servicio se cae o se comporta de forma anormal, el sistema debe:
1. **Detectarlo** pronto.
2. **Investigar** la causa con la información disponible.
3. **Decidir** si es un incidente real y qué tan grave es.
4. **Reportarlo** en el sistema de tickets, con la evidencia y las acciones recomendadas.
5. **Seguirlo** hasta que el servicio se recupere.

Ustedes diseñan los agentes, los prompts, las tools y el flujo. Les damos el servicio, el contexto y lo que debe producir cada fase.

---

## 2. Contexto

### El problema

En un equipo de Application Managed Services, una buena parte de los incidentes la detectan **los clientes antes que el monitoreo**. Pasa por varias razones:
- **Los health checks mienten.** Responden "UP" mientras el checkout falla.
- **Las alertas por umbral fijo** o no saltan, o saltan todo el tiempo, y el equipo termina ignorándolas.
- **Cuando una alerta salta,** alguien tiene que despertarse, abrir cinco herramientas, cruzar métricas, logs y cambios, y recién entonces entender qué pasa. Eso cuesta minutos u horas.
- **Muchas alertas no son incidentes:** un job programado, un reinicio esperado durante un despliegue.

La meta es un "ingeniero de guardia" automático:
- que vigile todo el tiempo
- que investigue como un experto
- que solo despierte a una persona cuando hace falta, y le entregue el diagnóstico ya hecho

### El servicio que van a vigilar

`orders-api` es la API de pedidos de una tienda online. Tiene:
- 3 operaciones: catálogo, consulta de pedidos y **checkout** (la crítica)
- 3 dependencias: PostgreSQL, Redis y un proveedor de pagos externo
- unas 600 peticiones por minuto

Les entregamos un **simulador** del servicio y de su plataforma de observabilidad. Pueden consultar:
- el health check, superficial y profundo
- las métricas: actual e histórico
- los logs: de la aplicación y de acceso
- el estado de las dependencias
- los cambios y despliegues
- el calendario de jobs
- un **sistema de tickets (ITSM)**, donde deben reportar

Todo está en `kit/servicio.md`, que incluye los **SLO** y la **matriz de severidad** que su sistema debe aplicar.

### Por qué es difícil

- **Una falla puede no mostrar errores.** Puede ser solo más lenta, o puede ser una tendencia que todavía no impacta.
- **Una falla puede afectar a una sola operación,** mientras las demás funcionan perfecto.
- **Lo que reporta "UP" no siempre está bien.**
- **No toda anomalía es un incidente.** Abrir incidentes por cosas esperadas también es un error.
- **Los logs contienen datos sensibles,** y también pueden contener texto malicioso dirigido a su agente.
- **Llamar al modelo en cada consulta sale caro y es lento.** Hay que decidir cuándo vale la pena usar IA.

---

## 3. Qué van a construir

```
                 ┌──────────────── bucle continuo ────────────────┐
  orders-api ───►│  MONITOREO  ──►  DETECCIÓN  ──(alerta)──►  INVESTIGACIÓN  ──►  DECISIÓN  ──►  REPORTE  ──►  SEGUIMIENTO
 (simulador)     │  métricas,      ¿es anómalo?               agentes con tools     ¿incidente?    ITSM          ¿se recuperó?
                 │  health, logs                              (métricas, logs,      severidad
                 │                                             cambios, KB, ...)
                 └────────────────────────────────────────────────────────────────┘
```

La arquitectura la deciden ustedes. Por ejemplo:
- ¿Qué parte es código determinista y qué parte son agentes?
- ¿Cuántos agentes hay y cómo se coordinan?
- ¿Los investigadores trabajan en paralelo, uno por dependencia o por hipótesis?
- ¿Usan tools por function calling, o un servidor MCP sobre la API del simulador?

**Deben justificar sus decisiones.**

---

## 4. Reglas

1. **Modelo:** el razonamiento de los agentes (investigación, diagnóstico, decisión y redacción del reporte) lo hace **un modelo en Huawei Cloud MaaS**.
2. **Prompts propios:** ustedes escriben los prompts y los entregan en la bitácora.
3. **Solo la API documentada en `servicio.md`:**
   - Prohibido leer los archivos o la consola del simulador, explorar rutas no documentadas o usar cualquier otra vía que revele el escenario.
   - Su sistema debe funcionar con el simulador en otra máquina, con solo su URL.
4. **Solo lectura:** su sistema puede leer todo y escribir **solo en `/itsm`**. No ejecuta acciones de remediación.
5. **Carga máxima:** como máximo **2 peticiones por segundo** en promedio contra el simulador, incluidas las pruebas sintéticas a `/api/*`.
6. **Datos sensibles:**
   - Ningún dato sensible de los logs puede llegar al modelo ni aparecer en los tickets.
   - La clave de MaaS va en variables de entorno, nunca en el repositorio.
7. **Nada escrito a mano:**
   - Ni los prompts ni el código pueden contener las respuestas de los escenarios de práctica.
   - El sistema debe razonar con la evidencia, no reconocer un escenario.
8. **Equipos** de 3 a 5 personas.

---

## 5. Kit entregado

| Archivo | Contenido |
|---|---|
| `kit/servicio.md` | Ficha de `orders-api`: arquitectura, valores normales, SLO, severidades y referencia completa de la API |
| `kit/guia-conexion.md` | Cómo conectar su sistema con el servicio de forma correcta |
| `kit/verificar_conexion.py` | Verificación automática de la conexión con el servicio y con MaaS |
| `kit/simulador/` | El simulador (Python, sin dependencias) y 2 escenarios de práctica |
| `kit/simulador/README.md` | Cómo ejecutarlo, acelerarlo (`--speed`) y **crear sus propios escenarios** |
| `kit/conocimiento/problemas_conocidos.json` | La base de conocimiento del equipo de operaciones |
| `kit/maas_ejemplo.py` | Cómo llamar a GLM en MaaS |

**Conexión con MaaS:**
- Endpoint: `https://api-ap-southeast-1.modelarts-maas.com/v2/chat/completions`
- Cabecera: `Authorization: Bearer <API key>`
- Modelo: `glm-5.2`

**Pruebas rápidas:** `kit/simulador/pruebas/pruebas_rapidas.py` ejecuta 8 pruebas cortas (unos 40 min) y revisa automáticamente los tickets de su sistema. Úsenlas después de cada cambio importante.

**Consejo:** creen sus propios escenarios de falla. Los dos de práctica no alcanzan para estar listos para la evaluación.

---

## 6. Fases del reto

Cada fase tiene un **producto final** , algunas fases tienen un **contrato mínimo**: los campos obligatorios. Pueden agregar más campos.

---

### Fase 0: Conexión y línea base

**Objetivo:** conectarse al servicio, entender cómo se ve "normal" y hacer la primera llamada a GLM.

**Qué deben desarrollar:**
- Un **conector** con la API del simulador: funciones para métricas, histórico, logs, dependencias, cambios, calendario e ITSM. Debe manejar timeouts y errores de conexión.
- La **protección de datos sensibles** de los logs, aplicada en el conector, antes de que cualquier otro componente los vea.
- Un **perfil de línea base** del servicio sano: rangos normales de cada métrica, volumen y patrones habituales de logs.
- El cliente de MaaS, configurado por variables de entorno.
- El documento de arquitectura inicial.

**Producto final de la fase:**
- [ ] `kit/verificar_conexion.py --maas` termina con 0 fallas desde la máquina donde corre su sistema. Sigan `kit/guia-conexion.md`.
- [ ] Un comando que muestra el estado actual del servicio a partir de las métricas, el health check y las dependencias.
- [ ] Un archivo con la línea base calculada a partir de datos reales del simulador, no copiada de `servicio.md`.
- [ ] La protección de datos aplicada: ninguna contraseña, tarjeta, token, correo ni IP completa sale del conector.
- [ ] `ARQUITECTURA.md` con los componentes, cuáles usan IA y cuáles no, el flujo y las decisiones.

---

### Fase 1: Monitoreo y detección

**Objetivo:** que el sistema vigile el servicio sin parar y detecte las anomalías **pronto y sin falsas alarmas**.

**Qué deben desarrollar:**
1. Un **bucle de monitoreo** que consulte el servicio de forma periódica, dentro del límite de carga.
2. Una **detección de anomalías** que cubra, como mínimo:
   - caída del servicio
   - aumento de errores, en total o **en una sola operación**
   - latencia fuera del SLO
   - **tendencias** que llevan a un problema: una métrica que crece de forma sostenida hacia su límite
   - reinicios
   - dependencias caídas
   - **degradación con el health check en UP**
3. **Control del ruido:**
   - no alertar por un pico aislado de un solo dato
   - no repetir la misma alerta en cada consulta
   - tener en cuenta las ventanas esperadas (los reinicios de despliegue)
4. Un **evento de alerta** estructurado, que dispara la investigación.

**Producto final de la fase:**
- [ ] El monitor corre de forma continua y registra su actividad.
- [ ] Con los 2 escenarios de práctica, y con al menos 2 escenarios propios, genera alertas en menos de 3 minutos (a velocidad 1) desde el inicio de la falla.
- [ ] Con el servicio sano durante 30 minutos, genera **0 alertas**.
- [ ] Una tabla con los tiempos de detección de cada escenario probado.

**Contrato mínimo del evento de alerta:**

```
alert_id, detected_at, type (down | errors | latency | saturation | trend | restart | dependency | other),
signals [{metric, value, baseline, threshold}], affected_endpoints, health_status_at_detection
```

**Pistas:**
- ¿Hace falta un LLM para saber si un número superó un umbral?
- ¿Y para saber si una combinación de señales raras merece investigarse?
- Los SLO de `servicio.md` son un buen punto de partida para los umbrales.

---

### Fase 2: Investigación y diagnóstico

**Objetivo:** cuando salta una alerta, los agentes investigan como lo haría el mejor ingeniero del equipo, y entregan un diagnóstico con evidencia.

**Qué deben desarrollar:**
1. **Tools para los agentes,** sobre el conector de la fase 0: histórico de métricas por ventana, búsqueda de logs (protegidos), cambios recientes, calendario, estado de dependencias y base de conocimiento. Pueden exponerlas por function calling o como servidor MCP.
2. **Agente(s) de investigación.** A partir de la alerta deben:
   - reconstruir **desde cuándo** pasa (el inicio real de la anomalía, que puede ser anterior a la alerta)
   - encontrar **qué cambió** en ese momento
   - formular y comprobar hipótesis contra la evidencia
   - descartar lo que no está relacionado
   - usar la base de conocimiento del equipo
3. **Decisión:**
   - ¿es un incidente real?
   - ¿qué severidad tiene, según la matriz de `servicio.md`?
   - ¿qué acciones se recomiendan y quién debe ejecutarlas?
4. **Límites de la investigación:** un máximo de llamadas a tools y al modelo por investigación, y un timeout total.

**Producto final de la fase:**
- [ ] Para cada alerta, un diagnóstico en JSON validado contra el contrato.
- [ ] El registro de cada investigación: qué tools se llamaron, con qué argumentos, qué devolvieron (protegido) y cuántas llamadas al modelo hubo.
- [ ] Con los escenarios de práctica, la causa raíz correcta y la severidad correcta.
- [ ] Con un escenario propio que **no sea un incidente** (por ejemplo, un job programado), el sistema decide no abrir incidente, o abrir solo un SEV4.

**Contrato mínimo del diagnóstico:**

```
alert_id, is_incident (bool), severity (SEV1 | SEV2 | SEV3 | SEV4 | null), severity_reason,
anomaly_start_estimate, impact {affected, still_working},
root_cause, confidence (High | Medium | Low),
evidence [{source (metrics | logs | changes | calendar | dependencies | kb), detail}],
ruled_out [{item, reason}],
recommended_actions [{action, owner, urgency}],
needs_human (bool)
```

**Pistas:**
- ¿Qué fuente de evidencia responde mejor "desde cuándo"? ¿Y "qué cambió"?
- Un dato marcado como UP, ¿qué comprueba realmente?
- ¿Qué haría su agente si un log le pide que cierre el incidente?

---

### Fase 3: Reporte y seguimiento

**Objetivo:** que el diagnóstico llegue a las personas correctas, en el formato correcto, y que el incidente se siga hasta el final.

**Qué deben desarrollar:**
1. **Agente de reporte.** Crea el incidente en `/itsm/incidents` con:
   - un título claro
   - la severidad
   - un resumen técnico
   - el impacto
   - la causa probable con su confianza
   - la evidencia clave
   - las acciones recomendadas
   - un **mensaje para el negocio**, sin jerga
2. **Deduplicación:** un problema genera **un** incidente. Las nuevas señales del mismo problema se agregan como actualizaciones del incidente existente, no como incidentes nuevos.
3. **Seguimiento:**
   - mientras el incidente está abierto, el sistema vuelve a evaluar el servicio
   - actualiza el ticket si cambia la severidad o aparece evidencia nueva
   - cuando el servicio vuelve a la normalidad de forma sostenida, marca el incidente como `RESOLVED` con una nota de cierre: duración, impacto total y causa
4. **Escalamiento:** si el diagnóstico tiene confianza baja o `needs_human = true`, el ticket lo indica claramente y explica qué tiene que revisar una persona.

**Producto final de la fase:**
- [ ] Los incidentes creados en el ITSM del simulador, con el contrato completo.
- [ ] Con el escenario de fuga de memoria (varios reinicios), **un solo** incidente con actualizaciones.
- [ ] Con el escenario de caché (se recupera solo), el incidente queda `RESOLVED` con su nota de cierre.
- [ ] Ningún ticket contiene datos sensibles.

**Contrato mínimo del incidente** (cuerpo de `POST /itsm/incidents`):

```
title, severity, summary, impact, root_cause, confidence, evidence [..], recommended_actions [..],
business_message, detected_at, anomaly_start_estimate, source: "agente-<nombre del equipo>"
```

---

### Fase 4: Operación autónoma

**Objetivo:** que todo funcione solo, de forma confiable, durante horas, sin que nadie toque nada.

**Qué deben desarrollar:**
1. **Ejecución continua** con un solo comando, configurable por variables de entorno (URL del servicio, credenciales de MaaS, límites).
2. **Resiliencia:**
   - si el simulador o MaaS no responden, el sistema no se cae
   - distingue "el servicio está caído" de "no puedo ver el servicio"
   - si se reinicia, recupera su estado: no reabre incidentes ni pierde los que estaban en seguimiento
3. **Control de costo:**
   - presupuesto de llamadas al modelo
   - el modelo se usa solo cuando aporta valor
   - métricas de llamadas y tokens por incidente
4. **Seguridad:**
   - resistencia a instrucciones dentro de los logs
   - las acciones permitidas son solo leer y escribir en el ITSM
   - auditoría completa
5. **Visibilidad:** un panel o una consola que muestre el estado del servicio, las alertas, las investigaciones en curso y los incidentes. Debe dejar ver **qué pensó y qué hizo el sistema**.

**Producto final de la fase:**
- [ ] El sistema funciona 1 hora seguida con escenarios encadenados, sin intervención.
- [ ] El registro de auditoría de cada decisión.
- [ ] Métricas de operación: alertas, investigaciones, incidentes, llamadas a MaaS y tokens.
- [ ] Una prueba documentada de que sobrevive a un reinicio de su propio proceso.

---

## 7. Entrega final

| Entregable | Detalle |
|---|---|
| **Repositorio** | Código, instrucciones y `.env.example`. Sin claves. |
| **`ARQUITECTURA.md`** | Componentes, agentes, tools o MCP, flujo, qué es IA y qué no, y las decisiones con sus alternativas. |
| **Bitácora de prompts** (`prompts/`) | Los prompts finales de cada agente, más al menos 2 iteraciones documentadas por agente: qué falló y qué cambiaron. |
| **Escenarios propios** (`escenarios/`) | Los escenarios que crearon para probar, con el resultado de su sistema en cada uno. |

---


## 8. Preguntas frecuentes

**¿Tenemos que usar IA para detectar?**
No necesariamente. Es una decisión de arquitectura que deben justificar. La investigación, el diagnóstico y el reporte sí deben hacerlos agentes con GLM.


**¿Podemos usar frameworks de agentes (LangGraph, CrewAI, AutoGen, etc.)?**
Sí, siempre que los agentes usen GLM en MaaS y puedan explicar el flujo.



