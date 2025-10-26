#!/usr/bin/env python3
"""
Clasificación semántica de GPCs usando embeddings + similitud coseno
Optimizado para GPU y términos médicos en español
"""

import json
import torch
import numpy as np
from sentence_transformers import SentenceTransformer
from pathlib import Path
from tqdm import tqdm
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Configuración
DATA_DIR = Path(__file__).parent.parent / "data"
DOCS_DIR = Path(__file__).parent.parent / "docs"
GOD_MODE_FILE = DATA_DIR / "gpc_links_god_mode.json"
OUTPUT_FILE = DOCS_DIR / "gpc_links_god_mode_classified.md"

# Taxonomía médica detallada
ESPECIALIDADES = {
    "Cirugía General": [
        "apendicitis", "hernias", "colecistitis", "abscesos", "laparotomía", "laparoscopia",
        "obstrucción intestinal", "hemorragia digestiva", "peritonitis", "cirugía",
        "abdomen agudo", "trauma abdominal", "infección sitio quirúrgico", "quemaduras"
    ],
    "Medicina Interna": [
        "diabetes", "hipertensión", "dislipidemia", "obesidad", "síndrome metabólico",
        "insuficiencia renal", "enfermedad renal", "anemia", "hepatitis", "cirrosis",
        "tuberculosis", "VIH", "SIDA", "neumonía", "EPOC", "asma", "enfermedad pulmonar",
        "trombosis", "embolia", "anticoagulación", "hipertiroidismo", "hipotiroidismo"
    ],
    "Pediatría": [
        "neonatal", "lactante", "niño", "pediátrica", "pediátrico", "recién nacido",
        "prematuridad", "bajo peso al nacer", "ictericia neonatal", "hiperbilirrubinemia",
        "diarrea aguda", "deshidratación", "desnutrición", "vacunación", "desarrollo infantil"
    ],
    "Ginecología y Obstetricia": [
        "embarazo", "gestación", "parto", "cesárea", "preeclampsia", "eclampsia",
        "amenaza de aborto", "aborto", "hemorragia obstétrica", "puerperio",
        "control prenatal", "cervicouterino", "mama", "mamario", "ovario", "útero",
        "menstruación", "menopausia", "anticoncepción", "planificación familiar"
    ],
    "Traumatología y Ortopedia": [
        "fractura", "luxación", "esguince", "trauma", "ortopédica", "ortopédico",
        "columna", "rodilla", "cadera", "hombro", "mano", "pie", "hueso",
        "articulación", "ligamento", "menisco", "prótesis", "osteomielitis"
    ],
    "Cardiología": [
        "cardio", "corazón", "infarto", "miocardio", "angina", "arritmia",
        "insuficiencia cardiaca", "valvular", "válvula", "endocarditis",
        "pericarditis", "hipertensión arterial", "coronaria", "stent"
    ],
    "Neurología": [
        "cerebro", "cerebral", "neurológ", "epilepsia", "convulsiones", "crisis convulsiva",
        "ictus", "evento vascular cerebral", "EVC", "cefalea", "migraña", "Parkinson",
        "Alzheimer", "demencia", "neuropatía", "esclerosis", "meningitis", "encefalitis"
    ],
    "Oftalmología": [
        "ojo", "ocular", "oftálm", "retina", "catarata", "glaucoma", "conjuntivitis",
        "blefaritis", "queratitis", "uveítis", "degeneración macular", "retinopatía",
        "agudeza visual", "visión", "estrabismo"
    ],
    "Otorrinolaringología": [
        "oído", "nariz", "garganta", "otitis", "rinosinusitis", "sinusitis", "faringitis",
        "amigdalitis", "laringitis", "vértigo", "mareo", "sordera", "hipoacusia",
        "epistaxis", "rinitis", "olfato", "audición", "ORL"
    ],
    "Urología": [
        "riñón", "vejiga", "próstata", "uretra", "uréter", "urología", "urológico",
        "cálculo renal", "litiasis", "infección urinaria", "IVU", "incontinencia urinaria",
        "hiperplasia prostática", "cáncer próstata", "pene", "testículo", "escroto"
    ],
    "Dermatología": [
        "piel", "dermatitis", "psoriasis", "acné", "eccema", "úlcera", "lesión cutánea",
        "melanoma", "carcinoma", "infección piel", "celulitis", "erisipela",
        "herpes", "varicela", "micosis", "hongos", "alopecia"
    ],
    "Psiquiatría": [
        "depresión", "ansiedad", "psicosis", "esquizofrenia", "bipolar", "psiquiátric",
        "salud mental", "suicidio", "adicción", "dependencia", "alcohol", "drogas",
        "trastorno mental", "demencia", "déficit atención", "TDAH", "autismo"
    ],
    "Medicina de Urgencias": [
        "urgencia", "emergencia", "trauma", "politraumatizado", "choque", "shock",
        "reanimación", "RCP", "ATLS", "paro cardiaco", "intoxicación", "envenenamiento",
        "mordedura", "picadura", "quemadura", "electrocución", "ahogamiento"
    ],
    "Anestesiología": [
        "anestesia", "anestésico", "sedación", "analgesia", "dolor agudo", "dolor crónico",
        "bloqueo", "espinal", "epidural", "intubación", "vía aérea", "ventilación"
    ],
    "Oncología": [
        "cáncer", "tumor", "neoplasia", "maligno", "metástasis", "quimioterapia",
        "radioterapia", "oncológic", "carcinoma", "sarcoma", "leucemia", "linfoma"
    ]
}

def mean_pooling(model_output, attention_mask):
    """Mean pooling para obtener sentence embeddings"""
    token_embeddings = model_output[0]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

def get_embedding(text: str, model):
    """Obtener embedding de un texto usando SentenceTransformer"""
    return model.encode(text, convert_to_tensor=True, normalize_embeddings=True)

def classify_gpc_semantic(title: str, especialidad_embeddings, model):
    """
    Clasificar GPC usando similitud coseno con embeddings de especialidades
    """
    # Obtener embedding del título
    title_embedding = get_embedding(title.lower(), model)
    
    # Calcular similitud con cada especialidad
    best_specialty = None
    best_score = -1
    
    for especialidad, emb in especialidad_embeddings.items():
        # Similitud coseno (embeddings ya normalizados)
        similarity = torch.dot(title_embedding, emb).item()
        
        if similarity > best_score:
            best_score = similarity
            best_specialty = especialidad
    
    # Convertir similitud coseno ([-1, 1]) a porcentaje de confianza
    confidence = ((best_score + 1) / 2) * 100  # Normalizar a [0, 100]
    
    return {
        "especialidad": best_specialty,
        "confianza": round(confidence, 1),
        "score_raw": round(best_score, 3)
    }

def create_especialidad_embeddings(model):
    """
    Crear embeddings representativos para cada especialidad
    basados en las palabras clave
    """
    print("🔧 Creando embeddings de especialidades...")
    especialidad_embeddings = {}
    
    for especialidad, keywords in ESPECIALIDADES.items():
        # Crear texto representativo de la especialidad
        representative_text = " ".join(keywords)
        
        # Obtener embedding
        embedding = get_embedding(representative_text, model)
        especialidad_embeddings[especialidad] = embedding
        
        print(f"   ✅ {especialidad}: {len(keywords)} términos clave")
    
    print()
    return especialidad_embeddings

def generate_markdown(classified_gpcs: list, output_file: Path):
    """
    Generar markdown organizado jerárquicamente
    """
    print("📝 Generando documento markdown...")
    
    # Agrupar por especialidad
    by_specialty = {}
    for gpc in classified_gpcs:
        specialty = gpc['classification']['especialidad']
        if specialty not in by_specialty:
            by_specialty[specialty] = []
        by_specialty[specialty].append(gpc)
    
    # Ordenar especialidades por número de GPCs
    sorted_specialties = sorted(by_specialty.items(), key=lambda x: len(x[1]), reverse=True)
    
    # Generar contenido
    lines = [
        "# 📚 Guías de Práctica Clínica - Clasificadas por Especialidad",
        "",
        f"**Total de GPCs:** {len(classified_gpcs)}",
        f"**Fecha de generación:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 📊 Resumen por Especialidad",
        "",
        "| Especialidad | Cantidad | % Total |",
        "|--------------|----------|---------|"
    ]
    
    for specialty, gpcs in sorted_specialties:
        percentage = (len(gpcs) / len(classified_gpcs)) * 100
        lines.append(f"| {specialty} | {len(gpcs)} | {percentage:.1f}% |")
    
    lines.extend(["", "---", ""])
    
    # Detalles por especialidad
    for specialty, gpcs in sorted_specialties:
        lines.append(f"## {specialty} ({len(gpcs)} GPCs)")
        lines.append("")
        
        # Ordenar por confianza
        gpcs_sorted = sorted(gpcs, key=lambda x: x['classification']['confianza'], reverse=True)
        
        for i, gpc in enumerate(gpcs_sorted, 1):
            title = gpc['title']
            conf = gpc['classification']['confianza']
            ger_url = gpc.get('ger_url', 'N/A')
            grr_url = gpc.get('grr_url', 'N/A')
            
            # Emoji según confianza
            if conf >= 80:
                emoji = "✅"
            elif conf >= 60:
                emoji = "⚠️"
            else:
                emoji = "❓"
            
            lines.append(f"### {i}. {emoji} {title}")
            lines.append(f"**Confianza:** {conf}%")
            
            if ger_url != 'N/A':
                lines.append(f"- 📄 **GER:** {ger_url}")
            if grr_url != 'N/A':
                lines.append(f"- 📄 **GRR:** {grr_url}")
            
            lines.append("")
        
        lines.append("---")
        lines.append("")
    
    # Escribir archivo
    output_file.write_text("\n".join(lines), encoding='utf-8')
    print(f"   ✅ Archivo generado: {output_file}")
    print()

def main():
    print("="*70)
    print("🧬 CLASIFICACIÓN SEMÁNTICA DE GPCs CON GPU")
    print("="*70)
    print()
    
    # Verificar GPU
    print("🔧 Verificando GPU...")
    print(f"   PyTorch version: {torch.__version__}")
    print(f"   CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"   GPU device: {torch.cuda.get_device_name(0)}")
        print(f"   GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    print()
    
    # Configurar dispositivo
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"🎯 Usando dispositivo: {device}")
    print()
    
    # Cargar GPCs
    print("📂 Cargando GPCs...")
    with open(GOD_MODE_FILE, 'r', encoding='utf-8') as f:
        gpcs = json.load(f)
    print(f"   ✅ {len(gpcs)} GPCs cargadas")
    print()
    
    # Cargar modelo de embeddings multilingüe
    print("🔄 Cargando modelo de embeddings...")
    print("   Modelo: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    model = SentenceTransformer(model_name, device=device)
    print(f"   ✅ Modelo cargado en {device}")
    print()
    
    # Crear embeddings de especialidades
    especialidad_embeddings = create_especialidad_embeddings(model)
    
    # Clasificar todas las GPCs
    print(f"🔍 Clasificando {len(gpcs)} GPCs...")
    classified_gpcs = []
    
    for gpc in tqdm(gpcs, desc="Clasificando"):
        title = gpc.get('title', 'Sin título')
        classification = classify_gpc_semantic(title, especialidad_embeddings, model)
        
        gpc_classified = gpc.copy()
        gpc_classified['classification'] = classification
        classified_gpcs.append(gpc_classified)
    
    print("\n✅ Clasificación completada")
    print()
    
    # Estadísticas
    print("📊 Estadísticas de clasificación:")
    by_specialty = {}
    for gpc in classified_gpcs:
        specialty = gpc['classification']['especialidad']
        by_specialty[specialty] = by_specialty.get(specialty, 0) + 1
    
    for specialty, count in sorted(by_specialty.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(classified_gpcs)) * 100
        print(f"   {specialty}: {count} GPCs ({percentage:.1f}%)")
    print()
    
    # Generar markdown
    generate_markdown(classified_gpcs, OUTPUT_FILE)
    
    # Guardar JSON con clasificaciones
    json_output = DATA_DIR / "gpc_links_god_mode_classified.json"
    with open(json_output, 'w', encoding='utf-8') as f:
        json.dump(classified_gpcs, f, indent=2, ensure_ascii=False)
    print(f"💾 JSON guardado: {json_output}")
    print()
    
    print("="*70)
    print("✅ PROCESO COMPLETADO")
    print("="*70)

if __name__ == "__main__":
    main()
