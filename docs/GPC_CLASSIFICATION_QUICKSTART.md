# 🔍 Guía Rápida - Clasificación de GPCs

## Archivos Principales

### Datos
```
data/
├── gpc_links_god_mode_classified.json          # ⭐ PRINCIPAL (373 GPCs clasificadas)
├── gpc_links_god_mode_classified_original.json # 📦 Backup pre-corrección
└── gpc_links_god_mode_classified_corrected.json # 🔄 Versión corregida (= principal)
```

### Documentación
```
docs/
├── gpc_links_god_mode_classified.md            # ⭐ DOCUMENTO PRINCIPAL (1952 líneas)
├── GPC_CLASSIFICATION_REPORT.md                # 📊 Reporte técnico detallado
└── GPC_CLASSIFICATION_FINAL_SUMMARY.md         # 📋 Resumen ejecutivo
```

### Scripts
```
scripts/
├── classify_gpcs_semantic.py           # 🚀 Clasificación completa (GPU)
├── test_classification_quick.py        # ⚡ Test rápido (5 GPCs)
├── analyze_classifications.py          # 🔍 Análisis de calidad
└── correct_classifications.py          # 🔧 Correcciones automáticas
```

## Uso Rápido

### Ver Estadísticas (PowerShell)
```powershell
# Contar GPCs por especialidad
$json = Get-Content data\gpc_links_god_mode_classified.json | ConvertFrom-Json
$stats = $json | Group-Object {$_.classification.especialidad} | 
         Select-Object Name, Count | 
         Sort-Object Count -Descending
$stats | Format-Table

# Ver GPCs de una especialidad específica
$json | Where-Object {$_.classification.especialidad -eq "Pediatría"} | 
        Select-Object title, @{N='Confianza';E={$_.classification.confianza}} |
        Format-Table -Wrap
```

### Reclasificar Todo
```bash
# Con ambiente conda activado (enarmgpu)
python scripts/classify_gpcs_semantic.py

# Aplicar correcciones
python scripts/correct_classifications.py

# Analizar resultados
python scripts/analyze_classifications.py
```

### Verificar GPU
```powershell
# PowerShell
C:\Users\datam\.conda\envs\enarmgpu\python.exe -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

## Estructura del JSON

```json
{
  "title": "Diagnóstico de apendicitis aguda",
  "ger_url": "https://...",
  "grr_url": "https://...",
  "classification": {
    "especialidad": "Cirugía General",
    "confianza": 83.2,
    "score_raw": 0.664,
    "correction": "manual_rule"  // Solo si fue corregida
  }
}
```

## Comandos Útiles

### Ver Top 10 GPCs por Confianza
```powershell
$json = Get-Content data\gpc_links_god_mode_classified.json | ConvertFrom-Json
$json | Sort-Object {$_.classification.confianza} -Descending | 
        Select-Object -First 10 title, 
        @{N='Especialidad';E={$_.classification.especialidad}}, 
        @{N='Conf%';E={$_.classification.confianza}} |
        Format-Table -Wrap
```

### Buscar GPCs por Palabra Clave
```powershell
$json = Get-Content data\gpc_links_god_mode_classified.json | ConvertFrom-Json
$keyword = "diabetes"
$json | Where-Object {$_.title -like "*$keyword*"} | 
        Select-Object title, @{N='Especialidad';E={$_.classification.especialidad}} |
        Format-Table -Wrap
```

### Exportar a CSV
```powershell
$json = Get-Content data\gpc_links_god_mode_classified.json | ConvertFrom-Json
$json | Select-Object title, 
        @{N='especialidad';E={$_.classification.especialidad}}, 
        @{N='confianza';E={$_.classification.confianza}},
        ger_url, grr_url |
        Export-Csv data\gpcs_clasificadas.csv -NoTypeInformation -Encoding UTF8
```

## Distribución Actual

| Especialidad | GPCs | % |
|--------------|------|---|
| Cirugía General | 52 | 13.9% |
| Medicina Interna | 52 | 13.9% |
| Pediatría | 45 | 12.1% |
| Ginecología y Obstetricia | 33 | 8.8% |
| Dermatología | 28 | 7.5% |
| Otorrinolaringología | 27 | 7.2% |
| Oncología | 23 | 6.2% |
| Traumatología y Ortopedia | 20 | 5.4% |
| Oftalmología | 20 | 5.4% |
| Neurología | 17 | 4.6% |
| Psiquiatría | 15 | 4.0% |
| Medicina de Urgencias | 15 | 4.0% |
| Urología | 15 | 4.0% |
| Cardiología | 8 | 2.1% |
| Anestesiología | 3 | 0.8% |

## Indicadores de Calidad

- ✅ **Alta confianza (≥80%):** 91 GPCs (24.4%)
- ⚠️ **Media confianza (60-79%):** 282 GPCs (75.6%)
- ❓ **Baja confianza (<60%):** 0 GPCs (0.0%)

## Siguiente Paso

👉 Abrir: `docs/gpc_links_god_mode_classified.md` para ver el documento completo organizado.

---
*Generado: 25 de octubre de 2025*
