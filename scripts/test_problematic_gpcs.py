#!/usr/bin/env python3
"""
Test para verificar GPCs problemáticas mencionadas por el usuario:
1. Acalasia - dice que no existe
2. Reflujo gastroesofágico - está confundida con dispepsia
3. Validar que inferencia use validación semántica
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from progressive_search_god_mode import SmartValidator, find_gpc_smart

def test_gpc(title: str, description: str):
    """Test individual de GPC"""
    print(f"\n{'='*80}")
    print(f"TEST: {description}")
    print(f"Título: {title}")
    print('='*80)
    
    validator = SmartValidator()
    if not validator.load_model():
        return
    
    # Buscar GRR
    print("\n🔍 [PASO 1] Buscando GRR...")
    grr_result = find_gpc_smart(title, 'GRR', validator)
    
    if grr_result:
        print(f"\n✅ GRR encontrada:")
        print(f"   URL: {grr_result.url}")
        print(f"   ID: {grr_result.gpc_id}")
        print(f"   Confianza: {grr_result.confidence:.1%}")
        print(f"   Similitud título: {grr_result.title_match:.1%}")
    else:
        print(f"\n❌ GRR NO encontrada")
    
    # Buscar GER (con inferencia si hay GRR)
    print(f"\n🔍 [PASO 2] Buscando GER...")
    ger_result = find_gpc_smart(
        title, 'GER', validator,
        paired_url=grr_result.url if grr_result else None
    )
    
    if ger_result:
        print(f"\n✅ GER encontrada:")
        print(f"   URL: {ger_result.url}")
        print(f"   ID: {ger_result.gpc_id}")
        print(f"   Confianza: {ger_result.confidence:.1%}")
        print(f"   Similitud título: {ger_result.title_match:.1%}")
        print(f"   Fuente: {ger_result.source}")
    else:
        print(f"\n❌ GER NO encontrada")
    
    # Verificar coherencia
    if grr_result and ger_result:
        if grr_result.gpc_id == ger_result.gpc_id:
            print(f"\n✅ IDs coherentes: {grr_result.gpc_id}")
        else:
            print(f"\n⚠️  IDs DIFERENTES:")
            print(f"   GRR: {grr_result.gpc_id}")
            print(f"   GER: {ger_result.gpc_id}")

if __name__ == '__main__':
    # Test 1: Acalasia (usuario dice que no existe)
    test_gpc(
        "Diagnóstico y tratamiento de la acalasia en adultos",
        "Acalasia (usuario dice que no existe o no se parece)"
    )
    
    # Test 2: Reflujo gastroesofágico (confundida con dispepsia)
    test_gpc(
        "Diagnóstico y tratamiento de la enfermedad por reflujo gastroesofágico en el adulto",
        "Reflujo gastroesofágico (confundida con dispepsia)"
    )
    
    # Test 3: Dispepsia (para comparar)
    test_gpc(
        "Diagnóstico y tratamiento de la dispepsia funcional",
        "Dispepsia funcional (para comparación)"
    )
