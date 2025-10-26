#!/usr/bin/env python3
"""
Utilidad para revisar y validar clasificaciones de GPCs
Muestra estadísticas y permite identificar casos que requieren revisión
"""

import json
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent.parent / "data"
CLASSIFIED_FILE = DATA_DIR / "gpc_links_god_mode_classified.json"

def analyze_classifications():
    """Analizar clasificaciones y generar estadísticas"""
    
    with open(CLASSIFIED_FILE, 'r', encoding='utf-8') as f:
        gpcs = json.load(f)
    
    print("="*70)
    print("📊 ANÁLISIS DE CLASIFICACIONES")
    print("="*70)
    print()
    
    # Estadísticas por especialidad
    by_specialty = defaultdict(list)
    confidence_ranges = {
        'alta': 0,      # >= 80%
        'media': 0,     # 60-79%
        'baja': 0       # < 60%
    }
    
    for gpc in gpcs:
        specialty = gpc['classification']['especialidad']
        confidence = gpc['classification']['confianza']
        
        by_specialty[specialty].append({
            'title': gpc['title'],
            'confidence': confidence
        })
        
        if confidence >= 80:
            confidence_ranges['alta'] += 1
        elif confidence >= 60:
            confidence_ranges['media'] += 1
        else:
            confidence_ranges['baja'] += 1
    
    # Mostrar estadísticas generales
    print("📈 Distribución de Confianza:")
    total = len(gpcs)
    print(f"   ✅ Alta (≥80%):   {confidence_ranges['alta']:3d} ({confidence_ranges['alta']/total*100:.1f}%)")
    print(f"   ⚠️  Media (60-79%): {confidence_ranges['media']:3d} ({confidence_ranges['media']/total*100:.1f}%)")
    print(f"   ❓ Baja (<60%):    {confidence_ranges['baja']:3d} ({confidence_ranges['baja']/total*100:.1f}%)")
    print()
    
    # Mostrar top especialidades
    print("🏥 Top 5 Especialidades:")
    sorted_specialties = sorted(by_specialty.items(), key=lambda x: len(x[1]), reverse=True)
    for i, (specialty, items) in enumerate(sorted_specialties[:5], 1):
        avg_conf = sum(item['confidence'] for item in items) / len(items)
        print(f"   {i}. {specialty:30s} {len(items):3d} GPCs (conf. promedio: {avg_conf:.1f}%)")
    print()
    
    # GPCs con baja confianza
    low_confidence = []
    for gpc in gpcs:
        if gpc['classification']['confianza'] < 60:
            low_confidence.append({
                'title': gpc['title'],
                'specialty': gpc['classification']['especialidad'],
                'confidence': gpc['classification']['confianza']
            })
    
    if low_confidence:
        print(f"❓ GPCs con Baja Confianza (<60%): {len(low_confidence)}")
        print("   (Recomendado: revisar manualmente estas clasificaciones)")
        print()
        for item in sorted(low_confidence, key=lambda x: x['confidence'])[:10]:
            title_short = item['title'][:60] + "..." if len(item['title']) > 60 else item['title']
            print(f"   • {title_short}")
            print(f"     → {item['specialty']} ({item['confidence']}%)")
            print()
    
    # Especialidades con pocas GPCs
    print("🔍 Especialidades con Pocas GPCs (<10):")
    for specialty, items in sorted_specialties:
        if len(items) < 10:
            avg_conf = sum(item['confidence'] for item in items) / len(items)
            print(f"   • {specialty}: {len(items)} GPCs (conf. promedio: {avg_conf:.1f}%)")
    print()
    
    # Confianza promedio por especialidad
    print("📊 Confianza Promedio por Especialidad:")
    specialty_confidence = []
    for specialty, items in by_specialty.items():
        avg_conf = sum(item['confidence'] for item in items) / len(items)
        specialty_confidence.append((specialty, avg_conf, len(items)))
    
    for specialty, avg_conf, count in sorted(specialty_confidence, key=lambda x: x[1], reverse=True)[:10]:
        emoji = "✅" if avg_conf >= 75 else "⚠️" if avg_conf >= 65 else "❓"
        print(f"   {emoji} {specialty:30s} {avg_conf:.1f}% ({count} GPCs)")
    
    print()
    print("="*70)

def find_misclassified():
    """Encontrar posibles clasificaciones incorrectas basadas en palabras clave obvias"""
    
    with open(CLASSIFIED_FILE, 'r', encoding='utf-8') as f:
        gpcs = json.load(f)
    
    # Patrones obvios de especialidad
    obvious_patterns = {
        'Pediatría': ['niño', 'neonato', 'lactante', 'pediátrica', 'pediátrico', 'recién nacido'],
        'Cardiología': ['cardio', 'corazón', 'infarto miocardio', 'coronaria'],
        'Neurología': ['cerebro', 'epilepsia', 'neurológ', 'convulsión', 'evento vascular cerebral'],
        'Oftalmología': ['ojo', 'ocular', 'oftálm', 'retina', 'visión'],
        'Ginecología y Obstetricia': ['embarazo', 'parto', 'cesárea', 'gestación', 'prenatal', 'obstétric']
    }
    
    print("\n" + "="*70)
    print("🔍 VERIFICACIÓN DE CLASIFICACIONES OBVIAS")
    print("="*70)
    print()
    
    potential_errors = []
    
    for gpc in gpcs:
        title_lower = gpc['title'].lower()
        classified_as = gpc['classification']['especialidad']
        confidence = gpc['classification']['confianza']
        
        for specialty, patterns in obvious_patterns.items():
            if any(pattern in title_lower for pattern in patterns):
                if classified_as != specialty:
                    potential_errors.append({
                        'title': gpc['title'],
                        'expected': specialty,
                        'classified_as': classified_as,
                        'confidence': confidence
                    })
    
    if potential_errors:
        print(f"⚠️  Encontradas {len(potential_errors)} posibles clasificaciones incorrectas:")
        print()
        for error in potential_errors[:15]:
            title_short = error['title'][:55] + "..." if len(error['title']) > 55 else error['title']
            print(f"   • {title_short}")
            print(f"     Clasificada como: {error['classified_as']} ({error['confidence']}%)")
            print(f"     Debería ser: {error['expected']}")
            print()
    else:
        print("✅ No se encontraron clasificaciones obvias incorrectas")
        print()
    
    print("="*70)

if __name__ == "__main__":
    analyze_classifications()
    find_misclassified()
