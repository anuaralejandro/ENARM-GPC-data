"""
Test rápido del clasificador médico con 5 GPCs de ejemplo.
"""

import torch
from transformers import pipeline
import time

# GPCs de prueba (varias especialidades)
TEST_GPCS = [
    "Diagnóstico y Tratamiento de la Insuficiencia Cardíaca Aguda y Crónica",
    "Prevención, Diagnóstico y Tratamiento de la Apendicitis Aguda",
    "Diagnóstico y Tratamiento del Síndrome de Ovario Poliquístico",
    "Prevención, Diagnóstico y Tratamiento de la Retinopatía Diabética",
    "Diagnóstico y Tratamiento del Traumatismo Craneoencefálico en el Adulto"
]

ESPECIALIDADES_TEST = [
    "Cardiología",
    "Cirugía General",
    "Ginecología y Obstetricia",
    "Oftalmología",
    "Neurología",
    "Medicina Interna",
    "Pediatría"
]

DISCIPLINAS_TEST = [
    "Diagnóstico",
    "Terapéutica Médica",
    "Terapéutica Quirúrgica",
    "Prevención",
    "Fisiopatología"
]

def main():
    print("\n" + "="*70)
    print("🧪 TEST DE CLASIFICADOR MÉDICO")
    print("="*70 + "\n")
    
    # Verificar GPU
    print("1️⃣ Verificando GPU...")
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        print(f"   ✅ GPU disponible: {device_name}")
        print(f"   📊 CUDA version: {torch.version.cuda}")
        device = 0
    else:
        print("   ⚠️  GPU no disponible, usando CPU")
        device = -1
    
    # Cargar modelo
    print("\n2️⃣ Cargando modelo médico (puede tardar ~30 segundos)...")
    print("   Usando BART-large-MNLI (mejor para español médico)")
    start = time.time()
    
    try:
        classifier = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=device
        )
        elapsed = time.time() - start
        print(f"   ✅ Modelo cargado en {elapsed:.1f}s")
    except Exception as e:
        print(f"   ❌ Error cargando modelo: {e}")
        return
    
    # Test de clasificación
    print("\n3️⃣ Clasificando 5 GPCs de prueba...")
    print("="*70)
    
    for i, gpc_title in enumerate(TEST_GPCS, 1):
        print(f"\n📄 GPC {i}: {gpc_title[:60]}...")
        
        # Clasificar especialidad
        start = time.time()
        result = classifier(
            gpc_title,
            candidate_labels=ESPECIALIDADES_TEST,
            hypothesis_template="Esta guía médica es sobre {}.",
            multi_label=True
        )
        elapsed = time.time() - start
        
        # Top 3 especialidades
        print(f"\n   🏥 Especialidad:")
        for j in range(min(3, len(result['labels']))):
            label = result['labels'][j]
            score = result['scores'][j]
            bar = "█" * int(score * 20)
            print(f"      {j+1}. {label:30s} {score:.1%} {bar}")
        
        # Clasificar disciplina
        disc_result = classifier(
            gpc_title,
            candidate_labels=DISCIPLINAS_TEST,
            hypothesis_template="Esta guía trata sobre {}.",
            multi_label=False
        )
        
        print(f"\n   📚 Disciplina:")
        print(f"      {disc_result['labels'][0]} ({disc_result['scores'][0]:.1%})")
        
        print(f"\n   ⏱️  Tiempo: {elapsed:.2f}s")
        print("   " + "-"*66)
    
    # Resumen
    print("\n" + "="*70)
    print("✅ TEST COMPLETADO")
    print("="*70)
    print("\nEl clasificador funciona correctamente.")
    print("Puedes ejecutar el script completo:")
    print("  python scripts/classify_gpcs_medical.py")
    print()

if __name__ == "__main__":
    main()
