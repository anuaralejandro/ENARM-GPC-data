#!/usr/bin/env python3
"""
Análisis de GPCs con confiabilidad <90% para validación cruzada
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple

# Cargar datos
json_path = Path("data/gpc_links_god_mode.json")
data = json.load(open(json_path, encoding='utf-8'))

# Filtrar GPCs con confiabilidad <90%
low_confidence_gpcs = []

for gpc in data:
    ger_conf = gpc.get('ger_confidence', 0)
    grr_conf = gpc.get('grr_confidence', 0)
    
    # Filtrar si alguna confiabilidad es <90% (pero >0%)
    if (0 < ger_conf < 90) or (0 < grr_conf < 90):
        low_confidence_gpcs.append({
            'title': gpc['title'],
            'ger_url': gpc.get('ger_url'),
            'grr_url': gpc.get('grr_url'),
            'ger_confidence': ger_conf,
            'grr_confidence': grr_conf,
            'ger_source': gpc.get('ger_source'),
            'grr_source': gpc.get('grr_source'),
            'ger_gpc_id': gpc.get('ger_gpc_id'),
            'grr_gpc_id': gpc.get('grr_gpc_id'),
            'min_confidence': min(ger_conf if ger_conf > 0 else 100, 
                                 grr_conf if grr_conf > 0 else 100)
        })

# Ordenar por confiabilidad mínima (ascendente)
low_confidence_gpcs.sort(key=lambda x: x['min_confidence'])

# Análisis estadístico
print("=" * 100)
print("📊 ANÁLISIS DE GPCs CON CONFIABILIDAD <90%")
print("=" * 100)
print()

print(f"📈 ESTADÍSTICAS GENERALES:")
print(f"   Total de GPCs procesadas: {len(data)}")
print(f"   GPCs con confiabilidad <90%: {len(low_confidence_gpcs)} ({len(low_confidence_gpcs)/len(data)*100:.1f}%)")
print()

# Distribución por rangos de confiabilidad
ranges = {
    '0-50%': 0,
    '50-60%': 0,
    '60-70%': 0,
    '70-80%': 0,
    '80-90%': 0
}

for gpc in low_confidence_gpcs:
    conf = gpc['min_confidence']
    if conf < 50:
        ranges['0-50%'] += 1
    elif conf < 60:
        ranges['50-60%'] += 1
    elif conf < 70:
        ranges['60-70%'] += 1
    elif conf < 80:
        ranges['70-80%'] += 1
    else:
        ranges['80-90%'] += 1

print("📊 DISTRIBUCIÓN POR RANGO DE CONFIABILIDAD:")
for range_name, count in ranges.items():
    bar = "█" * (count // 2)
    print(f"   {range_name:8} | {bar} {count} GPCs")
print()

# Análisis por fuente
source_analysis = defaultdict(lambda: {'count': 0, 'avg_conf': []})

for gpc in low_confidence_gpcs:
    # Analizar GER
    if gpc['ger_confidence'] > 0 and gpc['ger_confidence'] < 90:
        source = gpc.get('ger_source', 'Unknown')
        source_analysis[source]['count'] += 1
        source_analysis[source]['avg_conf'].append(gpc['ger_confidence'])
    
    # Analizar GRR
    if gpc['grr_confidence'] > 0 and gpc['grr_confidence'] < 90:
        source = gpc.get('grr_source', 'Unknown')
        source_analysis[source]['count'] += 1
        source_analysis[source]['avg_conf'].append(gpc['grr_confidence'])

print("🔍 ANÁLISIS POR FUENTE:")
for source, stats in sorted(source_analysis.items(), key=lambda x: x[1]['count'], reverse=True):
    avg = sum(stats['avg_conf']) / len(stats['avg_conf']) if stats['avg_conf'] else 0
    print(f"   {source:25} | {stats['count']:3} ocurrencias | Confiabilidad promedio: {avg:.1f}%")
print()

# Top 20 casos más críticos (menor confiabilidad)
print("🔴 TOP 20 CASOS MÁS CRÍTICOS (menor confiabilidad):")
print()
for i, gpc in enumerate(low_confidence_gpcs[:20], 1):
    print(f"{i:2}. [{gpc['min_confidence']:.1f}%] {gpc['title']}")
    
    if gpc['ger_confidence'] > 0 and gpc['ger_confidence'] < 90:
        print(f"    ⚠️  GER: {gpc['ger_confidence']:.1f}% | {gpc.get('ger_source', 'N/A')} | ID: {gpc.get('ger_gpc_id', 'N/A')}")
    
    if gpc['grr_confidence'] > 0 and gpc['grr_confidence'] < 90:
        print(f"    ⚠️  GRR: {gpc['grr_confidence']:.1f}% | {gpc.get('grr_source', 'N/A')} | ID: {gpc.get('grr_gpc_id', 'N/A')}")
    
    print()

# Guardar dataset de validación cruzada
output_path = Path("data/validation_cross_check_low_confidence.json")
json.dump(low_confidence_gpcs, open(output_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

print()
print("=" * 100)
print(f"✅ Dataset de validación guardado en: {output_path}")
print(f"   Total de casos para validación: {len(low_confidence_gpcs)}")
print("=" * 100)

# Generar reporte MD
md_lines = [
    "# Análisis de GPCs con Confiabilidad <90%",
    "",
    f"**Fecha**: {Path(json_path).stat().st_mtime}",
    f"**Total procesadas**: {len(data)}",
    f"**Con confiabilidad <90%**: {len(low_confidence_gpcs)} ({len(low_confidence_gpcs)/len(data)*100:.1f}%)",
    "",
    "## Distribución por Rango",
    "",
    "| Rango | Cantidad | Porcentaje |",
    "| ----- | -------- | ---------- |"
]

for range_name, count in ranges.items():
    pct = count / len(low_confidence_gpcs) * 100 if low_confidence_gpcs else 0
    md_lines.append(f"| {range_name} | {count} | {pct:.1f}% |")

md_lines.extend([
    "",
    "## Análisis por Fuente",
    "",
    "| Fuente | Ocurrencias | Conf. Promedio |",
    "| ------ | ----------- | -------------- |"
])

for source, stats in sorted(source_analysis.items(), key=lambda x: x[1]['count'], reverse=True):
    avg = sum(stats['avg_conf']) / len(stats['avg_conf']) if stats['avg_conf'] else 0
    md_lines.append(f"| {source} | {stats['count']} | {avg:.1f}% |")

md_lines.extend([
    "",
    "## Top 20 Casos Más Críticos",
    ""
])

for i, gpc in enumerate(low_confidence_gpcs[:20], 1):
    md_lines.append(f"### {i}. {gpc['title']} [{gpc['min_confidence']:.1f}%]")
    md_lines.append("")
    
    if gpc['ger_confidence'] > 0:
        md_lines.append(f"- **GER**: {gpc['ger_confidence']:.1f}% | {gpc.get('ger_source', 'N/A')} | ID: {gpc.get('ger_gpc_id', 'N/A')}")
        if gpc.get('ger_url'):
            md_lines.append(f"  - URL: {gpc['ger_url']}")
    
    if gpc['grr_confidence'] > 0:
        md_lines.append(f"- **GRR**: {gpc['grr_confidence']:.1f}% | {gpc.get('grr_source', 'N/A')} | ID: {gpc.get('grr_gpc_id', 'N/A')}")
        if gpc.get('grr_url'):
            md_lines.append(f"  - URL: {gpc['grr_url']}")
    
    md_lines.append("")

md_output = Path("docs/validation_low_confidence_analysis.md")
md_output.write_text('\n'.join(md_lines), encoding='utf-8')

print(f"📄 Reporte MD generado: {md_output}")
