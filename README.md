# Hackathon AMS: retos con GLM en Huawei Cloud MaaS

Dos retos para construir sistemas de agentes que ayuden a los equipos de Application Managed Services (AMS) a resolver incidentes.

| Reto | Qué se construye | Documento |
|---|---|---|
| **Reto 1: "El analista de incidentes que nunca duerme"** | Un sistema multiagente que analiza los logs de un incidente: ingesta, triage, causa raíz, resolución y comunicación | [`reto1/reto-hackathon-es.md`](reto1/reto-hackathon-es.md) |
| **Reto 2: "El guardia que nunca se duerme"** | Agentes que vigilan un servicio, detectan la falla, investigan la causa y la reportan solos | [`reto2/reto2-hackathon-es.md`](reto2/reto2-hackathon-es.md) |

## Estructura

```
reto1/
  reto-hackathon-es.md          el reto: contexto, fases, entregables y evaluación
  kit/                          logs del incidente, ticket, problemas conocidos, ejemplo de MaaS
reto2/
  reto2-hackathon-es.md         el reto: contexto, fases, entregables y evaluación
  kit/
    servicio.md                 ficha del servicio, SLO, severidades y referencia de la API
    simulador/                  servicio simulado y escenarios de práctica
    conocimiento/               base de conocimiento de operaciones
```

## Requisitos

- Python 3.9 o superior. El simulador del Reto 2 no necesita instalar nada.
- `requests` para el ejemplo de MaaS: `pip install requests`.
- Una clave de API de Huawei Cloud MaaS, que entrega la organización. Va en la variable de entorno `MAAS_API_KEY`, nunca en el código.

## Probar el simulador del Reto 2

```bash
cd reto2/kit/simulador
python simulador.py --speed 5 --scenario escenarios/practica-cache-caida.json --delay 60
# en otra terminal:
curl http://localhost:8080/metrics
```
