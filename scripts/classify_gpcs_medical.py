"""
GPC Medical Classifier - Sistema de Clasificación Automática de GPCs
====================================================================

Este módulo usa modelos de lenguaje médico (BioBERT/PubMedBERT) con PyTorch + GPU
para clasificar automáticamente las Guías de Práctica Clínica por:
- Especialidad médica (Cirugía, Cardiología, Pediatría, etc.)
- Disciplina (Anatomía, Fisiopatología, Inmunología, Terapéutica)
- Tema específico

Características:
- Zero-shot classification con modelos pre-entrenados
- Procesamiento por lotes en GPU
- Clasificación multi-etiqueta
- Confianza scores para validación
"""

import json
import torch
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    pipeline
)
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass
import pandas as pd
from tqdm import tqdm

# File paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"

GOD_MODE_JSON = DATA_DIR / "gpc_links_god_mode.json"
OUTPUT_JSON = DATA_DIR / "gpc_links_classified.json"
OUTPUT_MD = DOCS_DIR / "gpc_links_god_mode_FINAL.md"

# Taxonomía médica
ESPECIALIDADES = [
    "Cirugía General",
    "Cardiología",
    "Neurología",
    "Pediatría",
    "Ginecología y Obstetricia",
    "Medicina Interna",
    "Otorrinolaringología",
    "Oftalmología",
    "Urología",
    "Traumatología y Ortopedia",
    "Dermatología",
    "Gastroenterología",
    "Endocrinología",
    "Hematología",
    "Neumología",
    "Nefrología",
    "Reumatología",
    "Infectología",
    "Oncología",
    "Anestesiología",
    "Medicina de Urgencias",
    "Psiquiatría",
    "Rehabilitación",
    "Nutrición",
    "Medicina Crítica"
]

DISCIPLINAS = [
    "Anatomía",
    "Fisiopatología",
    "Farmacología",
    "Inmunología",
    "Microbiología",
    "Diagnóstico",
    "Terapéutica Médica",
    "Terapéutica Quirúrgica",
    "Prevención",
    "Rehabilitación"
]

@dataclass
class GPCClassification:
    """Resultado de clasificación de una GPC"""
    title: str
    especialidad: str
    especialidad_confidence: float
    especialidades_secundarias: List[Tuple[str, float]]
    disciplina: str
    disciplina_confidence: float
    tema_especifico: str
    ger_url: str = None
    grr_url: str = None


class MedicalGPCClassifier:
    """
    Clasificador de GPCs usando modelos médicos pre-entrenados.
    
    Usa un enfoque basado en NLI (Natural Language Inference) con modelos
    multilingües que entienden español médico.
    """
    
    def __init__(self, model_name: str = "facebook/bart-large-mnli"):
        """
        Inicializa el clasificador.
        
        Args:
            model_name: Nombre del modelo de HuggingFace
                      - facebook/bart-large-mnli (recomendado, entiende español)
                      - microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext
                      - dmis-lab/biobert-base-cased-v1.2
        """
        print(f"🔧 Inicializando clasificador médico...")
        print(f"   Modelo: {model_name}")
        
        # Detectar GPU
        self.device = 0 if torch.cuda.is_available() else -1
        device_name = torch.cuda.get_device_name(0) if self.device == 0 else "CPU"
        print(f"   Dispositivo: {device_name}")
        
        # Cargar modelo para zero-shot classification
        self.classifier = pipeline(
            "zero-shot-classification",
            model=model_name,
            device=self.device
        )
        
        print("✅ Clasificador listo\n")
    
    def classify_gpc(self, title: str) -> GPCClassification:
        """
        Clasifica una GPC por especialidad, disciplina y tema.
        
        Args:
            title: Título de la GPC
            
        Returns:
            GPCClassification con resultados
        """
        # Clasificar especialidad (top 3)
        especialidad_result = self.classifier(
            title,
            candidate_labels=ESPECIALIDADES,
            hypothesis_template="Esta guía médica es sobre {}.",
            multi_label=True
        )
        
        especialidad_principal = especialidad_result['labels'][0]
        especialidad_conf = especialidad_result['scores'][0]
        especialidades_secundarias = [
            (label, score) 
            for label, score in zip(especialidad_result['labels'][1:3], 
                                   especialidad_result['scores'][1:3])
            if score > 0.3  # Solo si tiene confianza significativa
        ]
        
        # Clasificar disciplina
        disciplina_result = self.classifier(
            title,
            candidate_labels=DISCIPLINAS,
            hypothesis_template="Esta guía trata sobre {}.",
            multi_label=False
        )
        
        disciplina = disciplina_result['labels'][0]
        disciplina_conf = disciplina_result['scores'][0]
        
        # Extraer tema específico (palabras clave del título)
        tema = self._extract_tema(title)
        
        return GPCClassification(
            title=title,
            especialidad=especialidad_principal,
            especialidad_confidence=especialidad_conf,
            especialidades_secundarias=especialidades_secundarias,
            disciplina=disciplina,
            disciplina_confidence=disciplina_conf,
            tema_especifico=tema
        )
    
    def _extract_tema(self, title: str) -> str:
        """
        Extrae el tema específico del título de la GPC.
        
        Args:
            title: Título de la GPC
            
        Returns:
            Tema específico extraído
        """
        # Palabras a ignorar
        stopwords = {
            'diagnóstico', 'tratamiento', 'prevención', 'manejo', 'abordaje',
            'de', 'del', 'la', 'el', 'en', 'y', 'a', 'o', 'para', 'con',
            'inicial', 'temprano', 'oportuno', 'integral', 'completo'
        }
        
        # Limpiar y extraer palabras clave
        words = title.lower().split()
        keywords = [w for w in words if w not in stopwords and len(w) > 3]
        
        # Tomar primeras palabras significativas
        tema = ' '.join(keywords[:5]) if keywords else title
        return tema.title()
    
    def classify_batch(self, gpcs: List[Dict]) -> List[GPCClassification]:
        """
        Clasifica un lote de GPCs.
        
        Args:
            gpcs: Lista de diccionarios con GPCs
            
        Returns:
            Lista de GPCClassification
        """
        results = []
        
        print(f"📊 Clasificando {len(gpcs)} GPCs...")
        
        for gpc in tqdm(gpcs, desc="Clasificando"):
            title = gpc.get('title', '')
            if not title:
                continue
                
            classification = self.classify_gpc(title)
            classification.ger_url = gpc.get('ger_url')
            classification.grr_url = gpc.get('grr_url')
            
            results.append(classification)
        
        print(f"✅ {len(results)} GPCs clasificadas\n")
        return results


def load_gpcs() -> List[Dict]:
    """Carga las GPCs desde el archivo JSON."""
    print("📂 Cargando GPCs desde God Mode JSON...")
    with open(GOD_MODE_JSON, 'r', encoding='utf-8') as f:
        gpcs = json.load(f)
    print(f"   ✅ {len(gpcs)} GPCs cargadas\n")
    return gpcs


def save_classifications(classifications: List[GPCClassification]):
    """Guarda las clasificaciones en JSON."""
    print("💾 Guardando clasificaciones...")
    
    data = []
    for c in classifications:
        data.append({
            'title': c.title,
            'especialidad': c.especialidad,
            'especialidad_confidence': c.especialidad_confidence,
            'especialidades_secundarias': c.especialidades_secundarias,
            'disciplina': c.disciplina,
            'disciplina_confidence': c.disciplina_confidence,
            'tema_especifico': c.tema_especifico,
            'ger_url': c.ger_url,
            'grr_url': c.grr_url
        })
    
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"   ✅ Guardado en: {OUTPUT_JSON}\n")


def generate_markdown(classifications: List[GPCClassification]):
    """
    Genera el documento Markdown final organizado por especialidad.
    
    Args:
        classifications: Lista de GPCClassification
    """
    print("📝 Generando Markdown final...")
    
    # Organizar por especialidad
    by_specialty = {}
    for c in classifications:
        if c.especialidad not in by_specialty:
            by_specialty[c.especialidad] = []
        by_specialty[c.especialidad].append(c)
    
    # Construir Markdown
    lines = []
    lines.append("# Guías de Práctica Clínica - Clasificadas por Especialidad")
    lines.append(f"\n**Fecha**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total GPCs**: {len(classifications)}")
    lines.append(f"**Especialidades**: {len(by_specialty)}")
    lines.append("\n---\n")
    
    # Tabla de contenidos
    lines.append("## 📑 Índice por Especialidad\n")
    for i, especialidad in enumerate(sorted(by_specialty.keys()), 1):
        count = len(by_specialty[especialidad])
        lines.append(f"{i}. [{especialidad}](#{especialidad.lower().replace(' ', '-')}) ({count} GPCs)")
    lines.append("\n---\n")
    
    # Estadísticas generales
    lines.append("## 📊 Estadísticas Generales\n")
    lines.append("### Por Especialidad\n")
    lines.append("| Especialidad | GPCs | % |")
    lines.append("|--------------|------|---|")
    
    total = len(classifications)
    for especialidad in sorted(by_specialty.keys(), key=lambda x: len(by_specialty[x]), reverse=True):
        count = len(by_specialty[especialidad])
        pct = (count / total) * 100
        lines.append(f"| {especialidad} | {count} | {pct:.1f}% |")
    
    lines.append("\n---\n")
    
    # Contenido por especialidad
    for especialidad in sorted(by_specialty.keys()):
        gpcs = by_specialty[especialidad]
        
        lines.append(f"\n## {especialidad}\n")
        lines.append(f"**Total**: {len(gpcs)} GPCs\n")
        
        # Organizar por disciplina dentro de especialidad
        by_discipline = {}
        for gpc in gpcs:
            if gpc.disciplina not in by_discipline:
                by_discipline[gpc.disciplina] = []
            by_discipline[gpc.disciplina].append(gpc)
        
        for disciplina in sorted(by_discipline.keys()):
            lines.append(f"\n### {disciplina}\n")
            
            for gpc in sorted(by_discipline[disciplina], key=lambda x: x.title):
                lines.append(f"\n#### {gpc.title}\n")
                
                # Tema específico
                lines.append(f"**Tema**: {gpc.tema_especifico}  ")
                
                # Confianza
                lines.append(f"**Confianza**: {gpc.especialidad_confidence:.1%}  ")
                
                # Especialidades secundarias
                if gpc.especialidades_secundarias:
                    secondary = ", ".join([f"{e} ({s:.1%})" for e, s in gpc.especialidades_secundarias])
                    lines.append(f"**También relacionado con**: {secondary}  ")
                
                # URLs
                if gpc.ger_url:
                    lines.append(f"📄 **GER**: {gpc.ger_url}  ")
                if gpc.grr_url:
                    lines.append(f"📄 **GRR**: {gpc.grr_url}  ")
                
                lines.append("")
        
        lines.append("\n---\n")
    
    # Escribir archivo
    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"   ✅ Guardado en: {OUTPUT_MD}\n")


def generate_statistics(classifications: List[GPCClassification]):
    """Genera estadísticas de clasificación."""
    print("\n" + "="*70)
    print("📊 ESTADÍSTICAS DE CLASIFICACIÓN")
    print("="*70 + "\n")
    
    # Por especialidad
    by_specialty = {}
    for c in classifications:
        by_specialty[c.especialidad] = by_specialty.get(c.especialidad, 0) + 1
    
    print("Top 10 Especialidades:")
    for i, (esp, count) in enumerate(sorted(by_specialty.items(), key=lambda x: x[1], reverse=True)[:10], 1):
        pct = (count / len(classifications)) * 100
        print(f"   {i:2d}. {esp:30s} {count:3d} ({pct:5.1f}%)")
    
    # Por disciplina
    by_discipline = {}
    for c in classifications:
        by_discipline[c.disciplina] = by_discipline.get(c.disciplina, 0) + 1
    
    print("\nDistribución por Disciplina:")
    for disc, count in sorted(by_discipline.items(), key=lambda x: x[1], reverse=True):
        pct = (count / len(classifications)) * 100
        print(f"   {disc:25s} {count:3d} ({pct:5.1f}%)")
    
    # Confianza promedio
    avg_conf = sum(c.especialidad_confidence for c in classifications) / len(classifications)
    print(f"\nConfianza promedio: {avg_conf:.1%}")
    
    # GPCs multi-especialidad
    multi = sum(1 for c in classifications if c.especialidades_secundarias)
    print(f"GPCs multi-especialidad: {multi} ({multi/len(classifications):.1%})")
    
    print("\n" + "="*70 + "\n")


def main():
    """Función principal."""
    print("\n" + "="*70)
    print("🏥 CLASIFICADOR AUTOMÁTICO DE GPCs")
    print("="*70 + "\n")
    
    # Cargar GPCs
    gpcs = load_gpcs()
    
    # Inicializar clasificador
    classifier = MedicalGPCClassifier()
    
    # Clasificar
    classifications = classifier.classify_batch(gpcs)
    
    # Guardar resultados
    save_classifications(classifications)
    
    # Generar Markdown
    generate_markdown(classifications)
    
    # Estadísticas
    generate_statistics(classifications)
    
    print("="*70)
    print("✅ PROCESO COMPLETADO")
    print("="*70)
    print(f"\nArchivos generados:")
    print(f"   1. {OUTPUT_JSON}")
    print(f"   2. {OUTPUT_MD}")
    print()


if __name__ == "__main__":
    main()
