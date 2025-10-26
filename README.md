# ENARM-GPC-data 🏥

Sistema de clasificación automática de Guías de Práctica Clínica (GPCs) del ENARM usando embeddings semánticos y aceleración GPU.

## 📑 Índice

- [📋 Acceso Rápido](#-acceso-rápido)
- [⚠️ Declaración y Contexto del Proyecto](#️-declaración-y-contexto-del-proyecto)
  - [Contexto Crítico](#contexto-crítico)
  - [El Problema Real](#el-problema-real)
- [📊 Resumen del Proyecto](#-resumen-del-proyecto)
  - [Características Principales](#características-principales)
- [🚀 Resultados](#-resultados)
  - [Distribución por Especialidad](#distribución-por-especialidad)
  - [Métricas de Confianza](#métricas-de-confianza)
- [🛠️ Instalación](#️-instalación)
  - [Requisitos](#requisitos)
  - [Setup Rápido](#setup-rápido)
- [📖 Uso](#-uso)
  - [Clasificación Rápida](#clasificación-rápida)
  - [Análisis de Calidad](#análisis-de-calidad)
  - [Corrección Automática](#corrección-automática)
- [📂 Estructura del Repositorio](#-estructura-del-repositorio)
- [🧪 Metodología](#-metodología)
  - [Modelo de Clasificación](#modelo-de-clasificación)
  - [Taxonomía de Especialidades](#taxonomía-de-especialidades)
- [📊 Archivos Clave](#-archivos-clave)
- [🔍 Ejemplos de Clasificación](#-ejemplos-de-clasificación)
- [🐛 Sistema de Corrección](#-sistema-de-corrección)
- [📈 Rendimiento](#-rendimiento)
- [🔬 Validación](#-validación)
- [📋 GPCs Faltantes](#-gpcs-faltantes)
- [🤝 Colaboración y Comunidad Médica](#-colaboración-y-comunidad-médica)
  - [¿Por Qué Colaborar?](#por-qué-colaborar)
  - [Cómo Puedes Contribuir](#-cómo-puedes-contribuir)
  - [Canales de Comunicación](#-canales-de-comunicación)
  - [Visión del Proyecto](#-visión-del-proyecto)
- [📝 Licencia](#-licencia)
- [📖 Cómo Citar](#-cómo-citar)
- [🙏 Agradecimientos](#-agradecimientos)
- [📧 Contacto](#-contacto)

---

## 📋 Acceso Rápido

<div align="center">

### 🔗 [**LINKS DE LAS GPCS CLASIFICADAS**](docs/gpc_links_god_mode_classified.md)

**373 GPCs organizadas por especialidad • 1,952 líneas • Confianza validada**

</div>

---

## ⚠️ Declaración y Contexto del Proyecto

Este proyecto surge como **protesta ante la incompetencia de CENETEC y su falta de actualización en recursos de automatización para la práctica médica y el ejercicio de la medicina estandarizada**.

### Contexto Crítico

-  **CENETEC ELIMINÓ EL CATÁLOGO MAESTRO DE GPCs** y no han hecho nada por restaurarlo o actualizarlo
-  **5+ meses sin catálogo oficial actualizado** - Información médica crítica inaccesible
-  CENETEC es un **organismo federal** con presupuesto y recursos ilimitados
-  Este sistema fue desarrollado por un **médico interno de pregrado**
-  Sin formación formal en programación, IA o ciencias de la computación
-  **9 días** fueron suficientes para recuperar y clasificar 373 GPCs con GPU

### El Problema Real

**CENETEC quitó el catálogo maestro** - el recurso central que médicos, residentes y estudiantes usaban para acceder a guías de práctica clínica estandarizadas. Simplemente lo eliminaron sin aviso, sin alternativa, sin explicación.

Si un estudiante de medicina sin conocimientos previos de programación puede:
- Recuperar 373 GPCs de fuentes dispersas
- Clasificarlas automáticamente por especialidad
- Crear un sistema de búsqueda funcional
- Todo en **9 días** con tecnología gratuita de código abierto

**¿Por qué un organismo federal especializado con presupuesto ilimitado no puede mantener un simple catálogo actualizado?**

Esta es una demostración de que las herramientas existen, son accesibles y funcionan. La falta de recursos actualizados **no es un problema técnico, es abandono institucional deliberado**.

**No le debo agradecimientos a CENETEC** - Han demostrado ser incompetentes en su función básica: mantener información médica crítica actualizada y accesible para quienes ejercen medicina en México.

---

## �📊 Resumen del Proyecto

Este repositorio contiene un sistema completo de búsqueda, validación y clasificación de Guías de Práctica Clínica (GPCs) mexicanas, con enfoque en el examen ENARM. El proyecto utiliza modelos de lenguaje multilingües y aceleración GPU para clasificar 373 GPCs en 15 especialidades médicas.

**Periodo de desarrollo**: 16 - 25 de octubre de 2025

### Características Principales

- ✅ **Clasificación GPU**: 114 GPCs/segundo usando RTX 4070 + CUDA 12.1
- 🎯 **Alta confianza**: 100% de clasificaciones con confianza ≥60%
- 🔧 **Corrección automática**: Sistema de reglas para detectar y corregir misclassificaciones obvias
- 📚 **15 especialidades**: Desde Cirugía General hasta Dermatología
- 🇪🇸 **Optimizado para español médico**: Usando modelos multilingües

## 🚀 Resultados

### Distribución por Especialidad

| Especialidad | GPCs | % Total |
|--------------|------|---------|
| Cirugía General | 52 | 13.9% |
| Medicina Interna | 52 | 13.9% |
| Pediatría | 45 | 12.1% |
| Ginecología y Obstetricia | 33 | 8.8% |
| Otras 11 especialidades | 191 | 51.3% |

### Métricas de Confianza

- **Alta confianza (≥80%)**: 91 GPCs (24.4%)
- **Confianza media (60-79%)**: 282 GPCs (75.6%)
- **Baja confianza (<60%)**: 0 GPCs (0%)

## 🛠️ Instalación

### Requisitos

- Python 3.9+
- GPU NVIDIA con soporte CUDA 12.1+
- 8GB VRAM recomendado
- Conda o venv

### Setup Rápido

```bash
# Clonar repositorio
git clone https://github.com/anuaralejandro/ENARM-GPC-data.git
cd ENARM-GPC-data

# Crear entorno conda (recomendado)
conda create -n enarmgpu python=3.11 -y
conda activate enarmgpu

# Instalar PyTorch con CUDA
conda install pytorch torchvision torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia -y

# Instalar dependencias
pip install -r requirements-gpc-classifier.txt
```

## 📖 Uso

### Clasificación Rápida

```python
from scripts.classify_gpcs_semantic import classify_gpcs

# Clasificar todas las GPCs
results = classify_gpcs()
print(f"Clasificadas: {len(results)} GPCs")
```

### Análisis de Calidad

```python
from scripts.analyze_classifications import analyze_quality

# Analizar distribución y detectar errores
stats = analyze_quality("data/gpc_links_god_mode_classified.json")
```

### Corrección Automática

```python
from scripts.correct_classifications import apply_corrections

# Aplicar reglas de corrección
corrected = apply_corrections("data/gpc_links_god_mode_classified.json")
print(f"Corregidas: {corrected} GPCs")
```

## 📂 Estructura del Repositorio

```
ENARM-GPC-data/
├── scripts/                    # Scripts de clasificación y análisis
│   ├── classify_gpcs_semantic.py      # Clasificador principal (GPU)
│   ├── analyze_classifications.py     # Análisis de calidad
│   ├── correct_classifications.py     # Sistema de correcciones
│   ├── find_gpc_*.py                  # Scripts de búsqueda
│   └── validate_*.py                  # Validadores de coherencia
├── data/                       # Datasets JSON
│   ├── gpc_links_god_mode_classified.json     # Clasificación final
│   └── gpc_links_god_mode_classified_corrected.json
├── docs/                       # Documentación técnica
│   ├── gpc_links_god_mode_classified.md       # Documento organizado (1952 líneas)
│   ├── GPC_CLASSIFICATION_REPORT.md           # Reporte técnico completo
│   ├── GPC_CLASSIFICATION_QUICKSTART.md       # Guía rápida
│   └── GPCS_FALTANTES.md                      # GPCs no encontradas
├── requirements-gpc-classifier.txt    # Dependencias
└── README.md                          # Este archivo
```

## 🧪 Metodología

### Modelo de Clasificación

El sistema utiliza **sentence-transformers** con el modelo `paraphrase-multilingual-MiniLM-L12-v2`:

1. **Embeddings semánticos**: Convierte títulos de GPCs a vectores de 384 dimensiones
2. **Cosine similarity**: Compara con embeddings de 15 especialidades médicas
3. **Normalización**: Convierte scores a porcentajes de confianza (0-100%)
4. **Corrección**: Aplica reglas basadas en palabras clave obvias

### Taxonomía de Especialidades

15 especialidades con 14-22 términos médicos cada una:

- Cirugía General
- Medicina Interna
- Pediatría
- Ginecología y Obstetricia
- Traumatología y Ortopedia
- Cardiología
- Neurología
- Gastroenterología
- Endocrinología
- Nefrología
- Neumología
- Psiquiatría
- Dermatología
- Medicina de Urgencias
- Medicina Preventiva

## 📊 Archivos Clave

### Dataset Principal

**`data/gpc_links_god_mode_classified.json`**
- 373 GPCs clasificadas
- Estructura: `{title, ger_url, grr_url, classification: {especialidad, confianza, score_raw}}`

### Documento Organizado

**`docs/gpc_links_god_mode_classified.md`**
- 1952 líneas
- Organizado por especialidad → disciplina → tema
- Indicadores de confianza: ✅ (≥80%), ⚠️ (70-79%), ❓ (60-69%)

### Reporte Técnico

**`docs/GPC_CLASSIFICATION_REPORT.md`**
- Metodología completa
- Resultados de validación
- Limitaciones y mejoras futuras

## 🔍 Ejemplos de Clasificación

```python
# Ejemplo 1: GPC de alta confianza
{
  "title": "Diagnóstico y Tratamiento del Infarto Agudo del Miocardio",
  "classification": {
    "especialidad": "Cardiología",
    "confianza": 95.2,
    "score_raw": 0.8543
  }
}

# Ejemplo 2: GPC corregida automáticamente
{
  "title": "Vacunación en Recién Nacidos",
  "classification": {
    "especialidad": "Pediatría",  # Corregido de "Medicina Preventiva"
    "confianza": 87.1,
    "correction": "pediatric_keywords"
  }
}
```

## 🐛 Sistema de Corrección

El sistema detecta y corrige automáticamente:

- **Pediatría**: niño, niña, recién nacido, lactante, neonatal
- **Ginecología**: embarazo, gestante, parto, prenatal, obstétrico
- **Cardiología**: corazón, cardiaco, infarto, arritmia
- **Neurología**: cerebro, neuronal, epilepsia, Parkinson
- **Oftalmología**: ojo, ocular, retina, catarata

21 correcciones aplicadas en el dataset actual.

## 📈 Rendimiento

### GPU (RTX 4070)
- **Velocidad**: 114 GPCs/segundo
- **Tiempo total**: 3.27 segundos para 373 GPCs
- **VRAM**: ~2GB utilizado
- **Precisión**: 24.4% alta confianza, 75.6% media

### CPU (Fallback)
- **Velocidad**: ~5-10 GPCs/segundo
- **Tiempo total**: ~40-60 segundos para 373 GPCs

## 🔬 Validación

### Tests de Calidad

```bash
# Analizar distribución de confianza
python scripts/analyze_classifications.py

# Validar coherencia
python scripts/validate_gpc_coherence.py

# Verificar GPCs de baja confianza
python scripts/analyze_low_confidence.py
```

### Métricas de Validación

- **Cobertura**: 373/~500 GPCs del catálogo CENETEC/IMSS
- **Consistencia**: 94.4% sin necesidad de corrección manual
- **Precisión estimada**: 85-90% basado en revisión de muestra

## 📋 GPCs Faltantes

~100+ GPCs del catálogo oficial no encontradas en búsquedas automatizadas.

Ver análisis completo en: `docs/GPCS_FALTANTES.md`

Checklist interactivo: `docs/GPCS_FALTANTES_CHECKLIST.md`

## 🤝 Colaboración y Comunidad Médica

**Este es un proyecto de colaboración entre médicos, por médicos y para médicos.** Los organismos institucionales nos dejan cada vez más desprotegidos ante la desactualización y precariedad de un catálogo de GPCs ya de por sí desactualizadas.

### ¿Por Qué Colaborar?

La unión y fraternidad entre médicos es nuestra mejor respuesta ante instituciones que abandonan sus responsabilidades. Si CENETEC no mantiene actualizado el catálogo, **nosotros lo haremos**.

### 🔧 Cómo Puedes Contribuir

#### 1. **Reportar GPCs Desactualizadas o con Links Rotos**

¿Encontraste un link que ya no funciona? ¿Una GPC con información desactualizada?

**Abre un Issue en GitHub:**
- Ve a: https://github.com/anuaralejandro/ENARM-GPC-data/issues
- Clic en "New Issue"
- Título: `[GPC Desactualizada] Nombre de la GPC`
- Descripción:
  ```
  GPC: [Nombre completo]
  Especialidad: [Ej. Cardiología]
  Problema: [Link roto / Información desactualizada / Otro]
  Link actual: [URL que no funciona]
  Link nuevo (si lo encontraste): [URL actualizada]
  Comentarios adicionales: [Lo que consideres importante]
  ```

#### 2. **Agregar GPCs Faltantes**

Si conoces GPCs que no están en el catálogo (ver `docs/GPCS_FALTANTES.md`):

**Comparte la información:**
- Abre un Issue con título: `[GPC Nueva] Nombre de la GPC`
- Incluye:
  - Título completo
  - Especialidad
  - Link GER (Guía de Evidencias y Recomendaciones)
  - Link GRR (Guía de Referencia Rápida)
  - Fuente (CENETEC/IMSS/otra)

#### 3. **Mejorar Clasificaciones**

¿Crees que una GPC está mal clasificada?

**Propón correcciones:**
- Issue con título: `[Reclasificación] Nombre de la GPC`
- Especialidad actual vs. Especialidad propuesta
- Justificación médica

#### 4. **Validación por Especialidad**

Si eres residente o especialista:

**Valida GPCs de tu especialidad:**
- Revisa las GPCs en `docs/gpc_links_god_mode_classified.md`
- Confirma que links funcionan
- Verifica que clasificación sea correcta
- Reporta discrepancias

#### 5. **Difusión**

**Ayuda a otros médicos:**
- Comparte este repositorio con compañeros
- Menciona en grupos de WhatsApp/Telegram de estudio
- Referencia en foros médicos (MedECC, Foros ENARM, etc.)

### 💬 Canales de Comunicación

- **Issues GitHub**: Para reportes técnicos y actualizaciones
- **Discussions GitHub**: Para dudas generales y propuestas
- **Pull Requests**: Para contribuciones de código (si sabes programar)

### 🎯 Visión del Proyecto

**Queremos crear el catálogo de GPCs más actualizado y accesible de México**, mantenido por la comunidad médica, no dependiente de instituciones que han demostrado no estar a la altura de sus responsabilidades.

### ⚖️ Código de Conducta

- Respeto entre colegas médicos
- Información verificada (no especulación)
- Colaboración constructiva
- Enfoque en mejorar el recurso para todos

### 📊 Impacto de tu Colaboración

Cada GPC que reportes, cada link que actualices, cada clasificación que corrijas:
- Ayuda a miles de estudiantes de medicina
- Apoya a médicos internos y residentes
- Mejora la práctica médica estandarizada en México
- Demuestra que la comunidad médica puede auto-organizarse

**Juntos somos más fuertes que cualquier institución incompetente.**

## 📝 Licencia

Proyecto académico - Uso educativo y de investigación.

Datos de GPCs pertenecen a CENETEC/IMSS/Secretaría de Salud México.

## � Cómo Citar

Si utilizas este trabajo en tu investigación o proyecto, por favor cita:

```bibtex
@misc{viramontes2025enarmgpc,
  author = {Viramontes Flores, Anuar Alejandro},
  title = {ENARM-GPC-data: Sistema de Clasificación Automática de Guías de Práctica Clínica},
  year = {2025},
  month = {octubre},
  publisher = {GitHub},
  howpublished = {\url{https://github.com/anuaralejandro/ENARM-GPC-data}},
  note = {373 GPCs clasificadas en 15 especialidades médicas usando embeddings semánticos y GPU}
}
```

**Formato APA:**
```
Viramontes Flores, A. A. (2025). ENARM-GPC-data: Sistema de Clasificación Automática 
de Guías de Práctica Clínica [Software]. GitHub. 
https://github.com/anuaralejandro/ENARM-GPC-data
```

**Formato texto:**
```
Viramontes Flores, Anuar Alejandro. (2025). "ENARM-GPC-data: Sistema de Clasificación 
Automática de Guías de Práctica Clínica". Octubre 2025. 
Disponible en: https://github.com/anuaralejandro/ENARM-GPC-data
```

##  Agradecimientos

**NO a CENETEC** - Este proyecto existe precisamente por su incompetencia y falta de actualización.

### Agradecimientos Reales

- **Hugging Face**: sentence-transformers library (código abierto accesible)
- **PyTorch**: Framework de deep learning (herramientas que SÍ funcionan)
- **NVIDIA**: Soporte CUDA para aceleración GPU (tecnología disponible para todos)
- **Comunidad Open Source**: Por hacer accesible la tecnología que organismos federales no saben aprovechar

## 📧 Contacto

**Autor**: Anuar Alejandro Viramontes Flores  
**GitHub**: [@anuaralejandro](https://github.com/anuaralejandro)  
**Proyecto**: ENARM-GPC-data  
**Fecha**: Octubre 2025

---

**Nota**: Este proyecto forma parte del ecosistema [ENARMQbank](https://github.com/anuaralejandro/ENARMQbank), un sistema integral de preparación para el examen ENARM.
