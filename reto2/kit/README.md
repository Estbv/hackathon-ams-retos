# Kit del Reto 2

| Archivo | Contenido |
|---|---|
| `servicio.md` | Ficha de `orders-api`: arquitectura, valores normales, SLO, matriz de severidad y referencia de la API |
| `simulador/simulador.py` | El servicio simulado al que se conectan sus agentes |
| `simulador/escenarios/` | 2 escenarios de práctica |
| `simulador/README.md` | Cómo ejecutar el simulador y crear escenarios |
| `conocimiento/problemas_conocidos.json` | Base de conocimiento del equipo de operaciones (KB-101 a KB-108) |
| `maas_ejemplo.py` | Llamada mínima a GLM en Huawei Cloud MaaS |

Inicio rápido:

```bash
cd simulador && python simulador.py --speed 5
# en otra terminal:
curl http://localhost:8080/metrics
```
