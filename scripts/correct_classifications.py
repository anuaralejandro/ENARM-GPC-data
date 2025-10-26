#!/usr/bin/env python3
"""
Corrección automática de clasificaciones basada en reglas y palabras clave obvias
"""

import json
from pathlib import Path
import re

DATA_DIR = Path(__file__).parent.parent / "data"
DOCS_DIR = Path(__file__).parent.parent / "docs"
CLASSIFIED_FILE = DATA_DIR / "gpc_links_god_mode_classified.json"
OUTPUT_FILE = DATA_DIR / "gpc_links_god_mode_classified_corrected.json"
MD_FILE = DOCS_DIR / "gpc_links_god_mode_classified.md"

# Reglas de corrección (en orden de prioridad)
CORRECTION_RULES = [
    # Pediatría - la más específica primero
    {
        'specialty': 'Pediatría',
        'keywords': ['niño', 'niños', 'neonato', 'lactante', 'pediátrica', 'pediátrico', 
                     'recién nacido', 'edad pediátrica', 'infancia', 'adolescente'],
        'priority': 1
    },
    # Ginecología y Obstetricia
    {
        'specialty': 'Ginecología y Obstetricia',
        'keywords': ['embarazo', 'gestación', 'prenatal', 'obstétric', 'parto', 'cesárea',
                     'puerperio', 'preeclampsia', 'eclampsia', 'cervicouterino'],
        'priority': 2
    },
    # Cardiología
    {
        'specialty': 'Cardiología',
        'keywords': ['infarto miocardio', 'infarto agudo del miocardio', 'IAM', 
                     'coronaria', 'angina de pecho', 'cardiaca'],
        'priority': 3
    },
    # Neurología
    {
        'specialty': 'Neurología',
        'keywords': ['epilepsia', 'evento vascular cerebral', 'EVC', 'ictus', 
                     'parálisis cerebral', 'meningitis', 'encefalitis'],
        'priority': 4
    },
    # Oftalmología
    {
        'specialty': 'Oftalmología',
        'keywords': ['retina', 'retinopatía', 'glaucoma', 'catarata', 'ojo', 'ocular'],
        'priority': 5
    }
]

def should_reclassify(title: str, current_specialty: str) -> tuple:
    """
    Determinar si una GPC debe ser reclasificada
    Returns: (should_reclassify: bool, new_specialty: str, reason: str)
    """
    title_lower = title.lower()
    
    # Verificar cada regla en orden de prioridad
    for rule in sorted(CORRECTION_RULES, key=lambda x: x['priority']):
        target_specialty = rule['specialty']
        keywords = rule['keywords']
        
        # Si ya está clasificada correctamente, no cambiar
        if current_specialty == target_specialty:
            continue
        
        # Verificar si el título contiene alguna palabra clave
        for keyword in keywords:
            if keyword in title_lower:
                # Encontramos una razón para reclasificar
                reason = f"Contiene '{keyword}' → {target_specialty}"
                return (True, target_specialty, reason)
    
    return (False, current_specialty, "")

def correct_classifications():
    """Corregir clasificaciones automáticamente"""
    
    print("="*70)
    print("🔧 CORRECCIÓN AUTOMÁTICA DE CLASIFICACIONES")
    print("="*70)
    print()
    
    # Cargar datos
    with open(CLASSIFIED_FILE, 'r', encoding='utf-8') as f:
        gpcs = json.load(f)
    
    print(f"📂 Cargadas {len(gpcs)} GPCs")
    print()
    
    # Aplicar correcciones
    corrections = []
    corrected_gpcs = []
    
    for gpc in gpcs:
        title = gpc['title']
        current_specialty = gpc['classification']['especialidad']
        current_confidence = gpc['classification']['confianza']
        
        should_change, new_specialty, reason = should_reclassify(title, current_specialty)
        
        if should_change:
            corrections.append({
                'title': title,
                'from': current_specialty,
                'to': new_specialty,
                'reason': reason,
                'old_confidence': current_confidence
            })
            
            # Actualizar clasificación
            gpc['classification']['especialidad'] = new_specialty
            gpc['classification']['confianza'] = 95.0  # Alta confianza en reglas explícitas
            gpc['classification']['correction'] = 'manual_rule'
        
        corrected_gpcs.append(gpc)
    
    # Mostrar correcciones
    print(f"✅ Se aplicaron {len(corrections)} correcciones:")
    print()
    
    for i, corr in enumerate(corrections, 1):
        title_short = corr['title'][:60] + "..." if len(corr['title']) > 60 else corr['title']
        print(f"{i:2d}. {title_short}")
        print(f"    {corr['from']} → {corr['to']}")
        print(f"    Razón: {corr['reason']}")
        print()
    
    # Guardar JSON corregido
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(corrected_gpcs, f, indent=2, ensure_ascii=False)
    
    print(f"💾 JSON corregido guardado: {OUTPUT_FILE}")
    
    # Regenerar markdown
    from classify_gpcs_semantic import generate_markdown
    generate_markdown(corrected_gpcs, MD_FILE)
    
    # Estadísticas finales
    print()
    print("📊 Distribución Final por Especialidad:")
    by_specialty = {}
    for gpc in corrected_gpcs:
        specialty = gpc['classification']['especialidad']
        by_specialty[specialty] = by_specialty.get(specialty, 0) + 1
    
    for specialty, count in sorted(by_specialty.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(corrected_gpcs)) * 100
        print(f"   {specialty:30s} {count:3d} GPCs ({percentage:.1f}%)")
    
    print()
    print("="*70)
    print("✅ CORRECCIÓN COMPLETADA")
    print("="*70)

if __name__ == "__main__":
    correct_classifications()
