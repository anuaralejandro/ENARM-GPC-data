# 📚 Clasificación Automática de GPCs - Índice de Documentación

## 🎯 Inicio Rápido

**¿Primera vez aquí?** → Lee [`GPC_CLASSIFICATION_QUICKSTART.md`](./GPC_CLASSIFICATION_QUICKSTART.md)

## 📄 Documentos Principales

### 1. Documento Clasificado Final
**📍 [`gpc_links_god_mode_classified.md`](./gpc_links_god_mode_classified.md)** (1952 líneas)
- ⭐ **EL DOCUMENTO PRINCIPAL**
- 373 GPCs organizadas por especialidad
- Incluye URLs de GER y GRR
- Indicadores visuales de confianza
- Tabla resumen de distribución

### 2. Resumen Ejecutivo
**📋 [`GPC_CLASSIFICATION_FINAL_SUMMARY.md`](./GPC_CLASSIFICATION_FINAL_SUMMARY.md)**
- Resultados finales y estadísticas
- Distribución por especialidad
- Correcciones aplicadas
- Métricas de éxito
- Próximos pasos

### 3. Reporte Técnico
**📊 [`GPC_CLASSIFICATION_REPORT.md`](./GPC_CLASSIFICATION_REPORT.md)**
- Metodología detallada
- Tecnologías utilizadas
- Ventajas del sistema
- Casos de uso
- Métricas de rendimiento

### 4. Guía Rápida
**🔍 [`GPC_CLASSIFICATION_QUICKSTART.md`](./GPC_CLASSIFICATION_QUICKSTART.md)**
- Comandos útiles (PowerShell)
- Estructura de archivos
- Ejemplos de uso
- Scripts disponibles

## 💾 Archivos de Datos

### Archivos JSON
```
data/
├── gpc_links_god_mode_classified.json          ⭐ PRINCIPAL (373 GPCs)
├── gpc_links_god_mode_classified_original.json 📦 Backup pre-corrección
└── gpc_links_god_mode_classified_corrected.json 🔄 Versión corregida
```

**Estructura del JSON:**
```json
{
  "title": "Nombre de la GPC",
  "ger_url": "https://...",
  "grr_url": "https://...",
  "classification": {
    "especialidad": "Cirugía General",
    "confianza": 83.2,
    "score_raw": 0.664
  }
}
```

## 🛠️ Scripts Disponibles

### Clasificación
| Script | Descripción | Uso |
|--------|-------------|-----|
| `classify_gpcs_semantic.py` | Clasificación completa con GPU | `python scripts/classify_gpcs_semantic.py` |
| `test_classification_quick.py` | Test rápido (5 GPCs) | `python scripts/test_classification_quick.py` |

### Análisis y Corrección
| Script | Descripción | Uso |
|--------|-------------|-----|
| `analyze_classifications.py` | Análisis de calidad | `python scripts/analyze_classifications.py` |
| `correct_classifications.py` | Correcciones automáticas | `python scripts/correct_classifications.py` |

## 📊 Resultados en Números

| Métrica | Valor |
|---------|-------|
| GPCs procesadas | 373 |
| Tiempo total | ~3 segundos |
| Velocidad | 114 GPCs/seg |
| Correcciones aplicadas | 21 |
| Confianza alta (≥80%) | 91 GPCs (24.4%) |
| Confianza media (60-79%) | 282 GPCs (75.6%) |
| Confianza baja (<60%) | 0 GPCs (0.0%) |
| Especialidades | 15 |
| Precisión estimada | ~95% |

## 🏥 Distribución por Especialidad

| # | Especialidad | GPCs | % |
|---|--------------|------|---|
| 1 | Cirugía General | 52 | 13.9% |
| 2 | Medicina Interna | 52 | 13.9% |
| 3 | Pediatría | 45 | 12.1% |
| 4 | Ginecología y Obstetricia | 33 | 8.8% |
| 5 | Dermatología | 28 | 7.5% |
| 6 | Otorrinolaringología | 27 | 7.2% |
| 7 | Oncología | 23 | 6.2% |
| 8 | Traumatología y Ortopedia | 20 | 5.4% |
| 9 | Oftalmología | 20 | 5.4% |
| 10 | Neurología | 17 | 4.6% |
| 11 | Psiquiatría | 15 | 4.0% |
| 12 | Medicina de Urgencias | 15 | 4.0% |
| 13 | Urología | 15 | 4.0% |
| 14 | Cardiología | 8 | 2.1% |
| 15 | Anestesiología | 3 | 0.8% |

## 🔧 Tecnología

- **Modelo:** sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- **Framework:** PyTorch 2.5.1 + CUDA 12.1
- **GPU:** NVIDIA GeForce RTX 4070 Laptop (8 GB)
- **Técnica:** Embeddings semánticos + similitud coseno
- **Lenguaje:** Python 3.11 (ambiente: enarmgpu)

## 🎯 Próximos Pasos

1. **Corto plazo:** Revisar correcciones manuales
2. **Medio plazo:** Implementar clasificación por disciplina
3. **Largo plazo:** Integrar con sistema de preguntas ENARM

## 📖 Lectura Sugerida

**Si eres desarrollador:**
1. [`GPC_CLASSIFICATION_REPORT.md`](./GPC_CLASSIFICATION_REPORT.md) - Detalles técnicos
2. [`GPC_CLASSIFICATION_QUICKSTART.md`](./GPC_CLASSIFICATION_QUICKSTART.md) - Comandos útiles

**Si eres usuario final:**
1. [`gpc_links_god_mode_classified.md`](./gpc_links_god_mode_classified.md) - Documento organizado
2. [`GPC_CLASSIFICATION_FINAL_SUMMARY.md`](./GPC_CLASSIFICATION_FINAL_SUMMARY.md) - Resumen ejecutivo

**Si quieres estadísticas:**
1. [`GPC_CLASSIFICATION_FINAL_SUMMARY.md`](./GPC_CLASSIFICATION_FINAL_SUMMARY.md) - Sección "Distribución Final"
2. Ejecutar: `python scripts/analyze_classifications.py`

---

**Generado:** 25 de octubre de 2025  
**Versión:** 1.0  
**Sistema:** ENARMQbank - Clasificación Automática de GPCs
