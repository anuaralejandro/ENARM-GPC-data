#!/usr/bin/env python3
"""
🔥 TEST EJECUTIVO: Prueba con 5 GPCs problemáticas conocidas

Valida funcionamiento end-to-end del sistema integral con casos reales.
"""

import sys
import os
from pathlib import Path

# Add parent dir to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Set environment variables
os.environ['GOOGLE_API_KEY'] = os.getenv('GOOGLE_API_KEY', '')
os.environ['GOOGLE_CSE_ID'] = os.getenv('GOOGLE_CSE_ID', '')

from progressive_search_god_mode import ProgressiveGPCFinder


def main():
    """Ejecuta búsqueda con 5 GPCs de prueba"""
    
    # Crear temario de prueba con 5 GPCs problemáticas conocidas
    test_temario = """# Test GPCs

## Casos de Prueba

- **GPC Enfermedad por Reflujo Gastroesofágico en el adulto**
- **GPC Enfermedad hemorroidal en el adulto**
- **GPC Tratamiento quirúrgico de la obesidad en adultos**
- **GPC Diagnóstico y tratamiento de la diabetes mellitus tipo 2**
- **GPC Infarto agudo de miocardio**
"""
    
    # Guardar temario temporal
    test_temario_path = REPO_ROOT / "data" / "test_temario_5gpcs.md"
    test_temario_path.parent.mkdir(parents=True, exist_ok=True)
    test_temario_path.write_text(test_temario, encoding='utf-8')
    
    print("\n" + "="*80)
    print("🔥 TEST EJECUTIVO: 5 GPCs Problemáticas")
    print("="*80)
    print("\nCasos de prueba:")
    print("1. Reflujo (acrónimo ERGE)")
    print("2. Hemorroidal (recencia: 2009 vs 2008)")
    print("3. Obesidad (core term: obesidad vs diabetes)")
    print("4. Diabetes tipo 2")
    print("5. Infarto (acrónimo IAM)")
    print()
    
    # Ejecutar búsqueda
    finder = ProgressiveGPCFinder(
        temario_path=str(test_temario_path),
        output_json='data/test_5gpcs_results.json',
        output_csv='data/test_5gpcs_results.csv',
        output_md='docs/test_5gpcs_results.md'
    )
    
    finder.run()
    
    print("\n" + "="*80)
    print("✅ TEST EJECUTIVO COMPLETADO")
    print("="*80)
    print("\nRevisa los archivos:")
    print("  - data/test_5gpcs_results.json")
    print("  - data/test_5gpcs_results.csv")
    print("  - docs/test_5gpcs_results.md")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
