#!/usr/bin/env python3
"""
Script para monitorear el progreso de búsqueda de GPCs en tiempo real.

Uso:
    python scripts/check_gpc_progress.py
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = REPO_ROOT / "data" / "gpc_links.json"

def main():
    if not JSON_PATH.exists():
        print("❌ Archivo gpc_links.json no encontrado")
        return
    
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    
    # Contar por estado
    ger_found = sum(1 for r in data if r.get('ger_url'))
    grr_found = sum(1 for r in data if r.get('grr_url'))
    both_found = sum(1 for r in data if r.get('ger_url') and r.get('grr_url'))
    
    # Contar por fuente
    cenetec_count = sum(1 for r in data if 'cenetec' in (r.get('ger_url') or '').lower())
    imss_count = sum(1 for r in data if 'imss.gob.mx' in (r.get('ger_url') or '').lower())
    
    print("=" * 80)
    print("📊 ESTADÍSTICAS DE BÚSQUEDA GPC")
    print("=" * 80)
    print(f"\n📚 Total procesados: {total}")
    print(f"\n✅ GER encontrados: {ger_found}/{total} ({ger_found/total*100:.1f}%)")
    print(f"✅ GRR encontrados: {grr_found}/{total} ({grr_found/total*100:.1f}%)")
    print(f"🎯 Ambos (GER+GRR): {both_found}/{total} ({both_found/total*100:.1f}%)")
    
    print(f"\n🌐 Por dominio (GER):")
    print(f"  CENETEC: {cenetec_count} ({cenetec_count/max(1,ger_found)*100:.1f}%)")
    print(f"  IMSS: {imss_count} ({imss_count/max(1,ger_found)*100:.1f}%)")
    
    # Últimos 5 procesados
    print(f"\n📝 Últimos 5 GPCs procesados:")
    for r in data[-5:]:
        title = r.get('title', 'Sin título')[:60]
        ger = "✅" if r.get('ger_url') else "❌"
        grr = "✅" if r.get('grr_url') else "❌"
        print(f"  {ger} {grr} {title}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
