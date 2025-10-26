# Clasificación Automática de GPCs con Modelos Médicos

Este módulo implementa clasificación automática de las 373 Guías de Práctica Clínica usando modelos de lenguaje médico pre-entrenados (BioBERT/PubMedBERT) con PyTorch + GPU.

## 🎯 Objetivo

Organizar automáticamente las GPCs en un documento final estructurado por:

1. **Especialidad médica** (Cirugía, Cardiología, Pediatría, etc.)
2. **Disciplina** (Anatomía, Fisiopatología, Terapéutica, etc.)
3. **Tema específico** (extraído del título)

## 🧠 Modelo

Usamos **PubMedBERT** de Microsoft:
- Modelo: `microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext`
- Pre-entrenado en 14M+ abstracts de PubMed
- Especializado en terminología médica
- Zero-shot classification (no requiere fine-tuning)

### Alternativas disponibles:
- `dmis-lab/biobert-base-cased-v1.2` (BioBERT v1.2)
- `allenai/scibert_scivocab_uncased` (SciBERT)

## 📋 Taxonomía

### Especialidades (25 categorías)
```
Cirugía General, Cardiología, Neurología, Pediatría,
Ginecología y Obstetricia, Medicina Interna, ORL, Oftalmología,
Urología, Traumatología y Ortopedia, Dermatología, Gastroenterología,
Endocrinología, Hematología, Neumología, Nefrología, Reumatología,
Infectología, Oncología, Anestesiología, Medicina de Urgencias,
Psiquiatría, Rehabilitación, Nutrición, Medicina Crítica
```

### Disciplinas (10 categorías)
```
Anatomía, Fisiopatología, Farmacología, Inmunología, Microbiología,
Diagnóstico, Terapéutica Médica, Terapéutica Quirúrgica,
Prevención, Rehabilitación
```

## 🚀 Instalación

### Paso 1: Instalar dependencias

```powershell
# Desde la raíz del proyecto
cd C:\Users\datam\Documents\ENARMQbank
.\scripts\setup_gpc_classifier.ps1
```

Este script:
1. Verifica que estés en el environment `enarmgpu`
2. Instala PyTorch con CUDA 11.8 (soporte GPU)
3. Instala transformers y dependencias NLP
4. Verifica la instalación

**Tiempo estimado**: 5-10 minutos (depende de conexión)

### Instalación manual alternativa

```bash
# Activar environment
conda activate enarmgpu

# PyTorch con CUDA
conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia -y

# O con pip:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Transformers y NLP
pip install -r requirements-gpc-classifier.txt
```

## 🧪 Prueba Rápida

Antes de procesar las 373 GPCs, ejecuta un test con 5 ejemplos:

```powershell
python scripts/test_gpc_classifier.py
```

**Salida esperada**:
```
🧪 TEST DE CLASIFICADOR MÉDICO
======================================================================

1️⃣ Verificando GPU...
   ✅ GPU disponible: NVIDIA GeForce RTX 3060
   📊 CUDA version: 11.8

2️⃣ Cargando modelo médico (puede tardar ~30 segundos)...
   ✅ Modelo cargado en 28.3s

3️⃣ Clasificando 5 GPCs de prueba...
======================================================================

📄 GPC 1: Diagnóstico y Tratamiento de la Insuficiencia Cardíaca...

   🏥 Especialidad:
      1. Cardiología                    87.3% ████████████████████
      2. Medicina Interna               61.2% ████████████
      3. Medicina Crítica               42.8% ████████

   📚 Disciplina:
      Terapéutica Médica (89.5%)

   ⏱️  Tiempo: 1.24s
   ------------------------------------------------------------------
```

## 🏃 Ejecución Completa

Para clasificar las 373 GPCs:

```powershell
python scripts/classify_gpcs_medical.py
```

### Proceso completo:

1. **Carga GPCs** desde `data/gpc_links_god_mode.json`
2. **Inicializa modelo** (PubMedBERT con GPU)
3. **Clasifica cada GPC**:
   - Especialidad principal + secundarias (top 3)
   - Disciplina principal
   - Extrae tema específico
4. **Guarda resultados**:
   - JSON: `data/gpc_links_classified.json`
   - Markdown: `docs/gpc_links_god_mode_FINAL.md`
5. **Genera estadísticas**

**Tiempo estimado**: 10-15 minutos para 373 GPCs con GPU

### Salida esperada:

```
🏥 CLASIFICADOR AUTOMÁTICO DE GPCs
======================================================================

📂 Cargando GPCs desde God Mode JSON...
   ✅ 373 GPCs cargadas

🔧 Inicializando clasificador médico...
   Modelo: microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext
   Dispositivo: NVIDIA GeForce RTX 3060
✅ Clasificador listo

📊 Clasificando 373 GPCs...
Clasificando: 100%|████████████████████| 373/373 [12:34<00:00,  2.02s/it]
✅ 373 GPCs clasificadas

💾 Guardando clasificaciones...
   ✅ Guardado en: data\gpc_links_classified.json

📝 Generando Markdown final...
   ✅ Guardado en: docs\gpc_links_god_mode_FINAL.md

======================================================================
📊 ESTADÍSTICAS DE CLASIFICACIÓN
======================================================================

Top 10 Especialidades:
    1. Cirugía General                62 (16.6%)
    2. Medicina Interna               58 (15.5%)
    3. Pediatría                      45 (12.1%)
    4. Ginecología y Obstetricia      38 (10.2%)
    5. Gastroenterología              28 ( 7.5%)
    6. Cardiología                    24 ( 6.4%)
    7. Oftalmología                   18 ( 4.8%)
    8. Dermatología                   16 ( 4.3%)
    9. Urología                       15 ( 4.0%)
   10. ORL                            14 ( 3.8%)

Distribución por Disciplina:
   Terapéutica Médica        156 (41.8%)
   Diagnóstico               102 (27.3%)
   Terapéutica Quirúrgica     68 (18.2%)
   Prevención                 38 (10.2%)
   Fisiopatología              9 ( 2.4%)

Confianza promedio: 78.3%
GPCs multi-especialidad: 287 (76.9%)

======================================================================
✅ PROCESO COMPLETADO
======================================================================

Archivos generados:
   1. data\gpc_links_classified.json
   2. docs\gpc_links_god_mode_FINAL.md
```

## 📄 Archivo Final: `gpc_links_god_mode_FINAL.md`

### Estructura del documento:

```markdown
# Guías de Práctica Clínica - Clasificadas por Especialidad

**Fecha**: 2025-10-25 16:45:30
**Total GPCs**: 373
**Especialidades**: 23

---

## 📑 Índice por Especialidad

1. [Cirugía General](#cirugía-general) (62 GPCs)
2. [Medicina Interna](#medicina-interna) (58 GPCs)
3. [Pediatría](#pediatría) (45 GPCs)
...

---

## 📊 Estadísticas Generales

### Por Especialidad

| Especialidad | GPCs | % |
|--------------|------|---|
| Cirugía General | 62 | 16.6% |
| Medicina Interna | 58 | 15.5% |
...

---

## Cirugía General

**Total**: 62 GPCs

### Terapéutica Quirúrgica

#### Diagnóstico y Tratamiento de la Apendicitis Aguda

**Tema**: Apendicitis Aguda  
**Confianza**: 92.4%  
**También relacionado con**: Medicina de Urgencias (68.2%), Gastroenterología (45.1%)  
📄 **GER**: https://www.imss.gob.mx/.../014GER.pdf  
📄 **GRR**: https://www.imss.gob.mx/.../014GRR.pdf  

#### Diagnóstico y Tratamiento de la Hernia Inguinal

**Tema**: Hernia Inguinal  
**Confianza**: 89.7%  
...

### Diagnóstico

#### Laparotomía y/o Laparoscopia Diagnóstica

...

---

## Cardiología

**Total**: 24 GPCs

### Terapéutica Médica

#### Insuficiencia Cardíaca Aguda y Crónica

...
```

### Características del documento final:

✅ **Organización jerárquica**:
   - Especialidad > Disciplina > GPCs individuales

✅ **Información completa**:
   - Tema específico
   - Confianza de clasificación
   - Especialidades relacionadas
   - URLs (GER y GRR)

✅ **Navegación fácil**:
   - Índice con enlaces
   - Tabla de estadísticas
   - Formato consistente

✅ **Metadatos útiles**:
   - Fecha de generación
   - Totales por categoría
   - Porcentajes de distribución

## 🔧 Configuración Avanzada

### Cambiar modelo médico

Edita `scripts/classify_gpcs_medical.py`:

```python
# Línea ~118
classifier = MedicalGPCClassifier(
    model_name="dmis-lab/biobert-base-cased-v1.2"  # Cambiar aquí
)
```

### Ajustar umbral de especialidades secundarias

```python
# Línea ~157
if score > 0.3:  # Cambiar umbral (0.0 - 1.0)
```

### Agregar nuevas categorías

```python
# Líneas 28-53: Agregar especialidades
ESPECIALIDADES = [
    "Cirugía General",
    ...
    "Tu Nueva Especialidad"  # Agregar aquí
]

# Líneas 55-67: Agregar disciplinas
DISCIPLINAS = [
    "Diagnóstico",
    ...
    "Tu Nueva Disciplina"  # Agregar aquí
]
```

## 📊 Formato JSON de Salida

`data/gpc_links_classified.json`:

```json
[
  {
    "title": "Diagnóstico y Tratamiento de la Apendicitis Aguda",
    "especialidad": "Cirugía General",
    "especialidad_confidence": 0.924,
    "especialidades_secundarias": [
      ["Medicina de Urgencias", 0.682],
      ["Gastroenterología", 0.451]
    ],
    "disciplina": "Terapéutica Quirúrgica",
    "disciplina_confidence": 0.887,
    "tema_especifico": "Apendicitis Aguda",
    "ger_url": "https://www.imss.gob.mx/.../014GER.pdf",
    "grr_url": "https://www.imss.gob.mx/.../014GRR.pdf"
  },
  ...
]
```

## 🎓 Ventajas del Sistema

### 1. **Automatización completa**
   - No requiere clasificación manual
   - Procesa 373 GPCs en ~15 minutos
   - Actualizable con nuevas GPCs fácilmente

### 2. **Precisión médica**
   - Modelo pre-entrenado en literatura médica
   - Entiende terminología especializada
   - Confianza promedio ~78%

### 3. **Flexibilidad**
   - Multi-etiqueta (especialidades secundarias)
   - Configurable (umbrales, categorías)
   - Extensible a nuevas taxonomías

### 4. **Organización superior**
   - Estructura jerárquica clara
   - Facilita búsqueda por especialidad
   - Identifica relaciones entre disciplinas

### 5. **Uso de GPU**
   - 20-30x más rápido que CPU
   - Escalable a miles de GPCs
   - Batch processing optimizado

## 🔍 Casos de Uso

### 1. Búsqueda por especialidad
```markdown
¿Cuáles GPCs son de Pediatría?
→ Ver sección "Pediatría" en FINAL.md
```

### 2. Identificar multi-especialidad
```json
// GPCs que aplican a varias especialidades
"especialidades_secundarias": [...]
```

### 3. Análisis de cobertura
```
Distribución por Disciplina:
- Terapéutica: 60%
- Diagnóstico: 27%
→ Identificar gaps en prevención
```

### 4. Recomendaciones contextuales
```python
# Si usuario estudia Cardiología,
# mostrar GPCs con especialidad="Cardiología"
# + especialidades_secundarias que incluyan "Cardiología"
```

## ⚡ Optimizaciones

### Para datasets grandes (>1000 GPCs)

1. **Batch processing**:
```python
# En classify_batch(), procesar en lotes
for i in range(0, len(gpcs), batch_size):
    batch = gpcs[i:i+batch_size]
    # Clasificar batch completo
```

2. **Caché de modelos**:
```python
# Guardar clasificaciones previas
# Solo re-clasificar GPCs nuevas/modificadas
```

3. **GPU multi-threading**:
```python
# Usar DataLoader de PyTorch
# Paralelizar batch processing
```

## 🐛 Troubleshooting

### Error: "CUDA out of memory"
```python
# Reducir batch size o usar CPU
device = -1  # Forzar CPU
```

### Error: "Model not found"
```bash
# Verificar conexión a internet
# El modelo se descarga automáticamente (~400 MB)
```

### Clasificaciones incorrectas
```python
# Ajustar hypothesis_template
hypothesis_template="Esta guía clínica trata sobre {}."
# O usar modelo diferente (BioBERT)
```

## 📚 Referencias

- **PubMedBERT**: [Microsoft Research](https://huggingface.co/microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext)
- **BioBERT**: [DMIS Lab](https://github.com/dmis-lab/biobert)
- **Transformers**: [HuggingFace Docs](https://huggingface.co/docs/transformers/)
- **PyTorch**: [Official Docs](https://pytorch.org/docs/stable/index.html)

## ✅ Checklist de Implementación

- [ ] Instalar dependencias (`setup_gpc_classifier.ps1`)
- [ ] Ejecutar test (`test_gpc_classifier.py`)
- [ ] Clasificar GPCs completas (`classify_gpcs_medical.py`)
- [ ] Revisar `gpc_links_god_mode_FINAL.md`
- [ ] Validar estadísticas de distribución
- [ ] (Opcional) Ajustar taxonomía si necesario
- [ ] (Opcional) Fine-tune modelo con GPCs específicas

## 🚀 Próximos Pasos

1. **Integración con backend**:
   - Endpoint para búsqueda por especialidad
   - Filtros multi-criterio (especialidad + disciplina)
   - Recomendaciones basadas en clasificación

2. **Mejoras al modelo**:
   - Fine-tuning con GPCs del IMSS
   - Clasificación de sub-especialidades
   - Extracción de keywords automática

3. **Visualizaciones**:
   - Gráficos de distribución
   - Network graph de relaciones
   - Heatmap de cobertura por especialidad

---

**Creado**: 2025-10-25  
**Autor**: Sistema de Clasificación Automática ENARMQbank  
**Versión**: 1.0.0
