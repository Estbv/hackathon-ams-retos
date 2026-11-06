# Kit del Reto 2

| Archivo | Contenido |
|---|---|
| `servicio.md` | Ficha de `orders-api`: arquitectura, valores normales, SLO, matriz de severidad y referencia de la API |
| `guia-conexion.md` | **Cómo conectar su sistema con el servicio:** configuración, plan de consultas, tiempo, errores, ITSM, tools y lista de comprobación |
| `verificar_conexion.py` | Verifica automáticamente la conexión con el servicio y con MaaS |
| `simulador/simulador.py` | El servicio simulado al que se conectan sus agentes |
| `simulador/escenarios/` | 2 escenarios de práctica |
| `simulador/README.md` | Cómo ejecutar el simulador, crear escenarios y usar las pruebas rápidas |
| `simulador/pruebas/` | 8 pruebas cortas con revisión automática de los tickets de su sistema |
| `conocimiento/problemas_conocidos.json` | Base de conocimiento del equipo de operaciones (KB-101 a KB-108) |
| `maas_ejemplo.py` | Llamada mínima a GLM en Huawei Cloud MaaS |

Inicio rápido:

```bash
cd simulador && python simulador.py --speed 5
# en otra terminal, desde kit/:
python verificar_conexion.py --url http://localhost:8080 --maas
```
