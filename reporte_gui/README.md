# Visualizador de Reporte Docente (PySide6)

Este proyecto abre el archivo `data/Libro1.csv` y muestra:

- Lista de docentes con ID, nombre y departamento.
- Cantidad de dias con marca y total de marcas.
- Panel de detalle por docente con marcas por dia.
- Busqueda por nombre, ID o departamento.

## 1. Instalar dependencias

Desde la raiz del workspace:

```powershell
.\reporte\Scripts\python.exe -m pip install -r .\reporte_gui\requirements.txt
```

## 2. Ejecutar la app

```powershell
.\reporte\Scripts\python.exe .\reporte_gui\main.py
```

## Notas

- La app toma los datos de `data/Libro1.csv`.
- Si cambias el archivo, usa el boton `Recargar`.
