#!/usr/bin/env python3
"""
Analizar distribución de confianza en gpc_links.json
"""
import json

# Cargar GPCs
with open('data/gpc_links.json', encoding='utf-8') as f:
    gpcs = json.load(f)

# Clasificar por confianza mínima
bajo = []  # <70%
medio = []  # 70-85%
alto = []  # ≥85%

for gpc in gpcs:
    ger_conf = gpc.get('ger_confidence', 0)
    grr_conf = gpc.get('grr_confidence', 0)
    min_conf = min(ger_conf, grr_conf)
    
    if min_conf < 70:
        bajo.append((gpc['title'], ger_conf, grr_conf))
    elif min_conf < 85:
        medio.append((gpc['title'], ger_conf, grr_conf))
    else:
        alto.append((gpc['title'], ger_conf, grr_conf))

total = len(gpcs)

print("\n" + "="*80)
print("📊 DISTRIBUCIÓN DE CONFIANZA (mínimo de GER y GRR)")
print("="*80 + "\n")

print(f"  <70% (BAJO):    {len(bajo):3d} ({len(bajo)*100/total:5.1f}%)  ❌")
print(f"  70-85% (MEDIO): {len(medio):3d} ({len(medio)*100/total:5.1f}%)  ⚠️")
print(f"  ≥85% (ALTO):    {len(alto):3d} ({len(alto)*100/total:5.1f}%)  ✅")
print(f"  {'─'*60}")
print(f"  TOTAL:          {total:3d}")

# 10 ejemplos más bajos
print("\n" + "="*80)
print("📉 10 GPCs CON CONFIANZA MÁS BAJA")
print("="*80 + "\n")

bajo_sorted = sorted(bajo, key=lambda x: min(x[1], x[2]))
for i, (titulo, ger, grr) in enumerate(bajo_sorted[:10], 1):
    min_conf = min(ger, grr)
    print(f"{i:2d}. {titulo[:55]:<55} GER:{ger:5.1f}% GRR:{grr:5.1f}%  Min:{min_conf:5.1f}%")

# Analizar por qué son bajos
print("\n" + "="*80)
print("🔍 ANÁLISIS DE CASOS BAJOS")
print("="*80 + "\n")

ger_bajo = sum(1 for t, g, r in bajo if g < 70)
grr_bajo = sum(1 for t, g, r in bajo if r < 70)
ambos_bajo = sum(1 for t, g, r in bajo if g < 70 and r < 70)

print(f"  Solo GER <70%:        {ger_bajo - ambos_bajo:3d}")
print(f"  Solo GRR <70%:        {grr_bajo - ambos_bajo:3d}")
print(f"  Ambos (GER+GRR) <70%: {ambos_bajo:3d}")
print(f"  {'─'*60}")
print(f"  Total <70%:           {len(bajo):3d}")

# Distribución detallada
print("\n" + "="*80)
print("📊 DISTRIBUCIÓN DETALLADA")
print("="*80 + "\n")

rangos = [
    (0, 50, "Muy bajo"),
    (50, 60, "Bajo"),
    (60, 70, "Regular"),
    (70, 75, "Aceptable"),
    (75, 80, "Bueno"),
    (80, 85, "Muy bueno"),
    (85, 90, "Excelente"),
    (90, 100, "Óptimo"),
]

for min_r, max_r, label in rangos:
    count = sum(1 for gpc in gpcs 
                if min_r <= min(gpc.get('ger_confidence', 0), gpc.get('grr_confidence', 0)) < max_r)
    pct = count * 100 / total
    bar = "█" * int(pct / 2)
    print(f"  {min_r:2d}-{max_r:2d}% {label:<12} {count:3d} ({pct:5.1f}%) {bar}")

print("\n")
