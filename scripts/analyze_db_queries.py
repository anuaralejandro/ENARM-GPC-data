#!/usr/bin/env python3
"""
Script para analizar queries DB ejecutadas por endpoints específicos
Intercepta queries SQLAlchemy y analiza patrones N+1
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import httpx
import time
from typing import List, Dict
from contextlib import contextmanager
from sqlalchemy import event, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from backend.database import get_db, get_database_url
import threading
import json

# Storage global para queries capturadas
captured_queries = []
query_lock = threading.Lock()

def capture_query(conn, cursor, statement, parameters, context, executemany):
    """Captura queries SQL ejecutadas"""
    with query_lock:
        captured_queries.append({
            "timestamp": time.time(),
            "statement": statement,
            "parameters": parameters,
            "thread_id": threading.get_ident(),
            "stack_summary": []  # Se puede añadir traceback si necesario
        })

@contextmanager
def query_interceptor():
    """Context manager para interceptar queries"""
    global captured_queries
    captured_queries = []

    # Registrar listener
    event.listen(Engine, "before_cursor_execute", capture_query)

    try:
        yield captured_queries
    finally:
        # Desregistrar listener
        event.remove(Engine, "before_cursor_execute", capture_query)

async def analyze_endpoint_queries(endpoint_path: str, method: str = "GET", headers: Dict = None) -> Dict:
    """Analiza queries ejecutadas por un endpoint específico"""
    print(f"🔍 Analizando {method} {endpoint_path}")

    base_url = "http://127.0.0.1:8000"

    with query_interceptor() as queries:
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
                start_time = time.perf_counter()

                if method == "GET":
                    response = await client.get(endpoint_path, headers=headers or {})
                else:
                    response = await client.post(endpoint_path, headers=headers or {})

                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000

                # Pequeña pausa para capturar todas las queries
                await asyncio.sleep(0.1)

        except Exception as e:
            return {
                "endpoint": endpoint_path,
                "error": str(e),
                "queries": [],
                "analysis": {}
            }

    # Analizar queries capturadas
    analysis = analyze_query_patterns(queries)

    result = {
        "endpoint": endpoint_path,
        "method": method,
        "status_code": response.status_code if 'response' in locals() else None,
        "latency_ms": round(latency_ms, 2) if 'latency_ms' in locals() else None,
        "total_queries": len(queries),
        "queries": [
            {
                "statement": q["statement"],
                "parameters": q["parameters"]
            } for q in queries
        ],
        "analysis": analysis
    }

    return result

def analyze_query_patterns(queries: List[Dict]) -> Dict:
    """Analiza patrones en las queries para detectar N+1 y optimizaciones"""
    if not queries:
        return {"pattern": "no_queries", "recommendations": []}

    # Agrupar queries similares
    query_groups = {}
    for query in queries:
        # Normalizar query (remover parámetros específicos)
        normalized = normalize_query(query["statement"])
        if normalized not in query_groups:
            query_groups[normalized] = []
        query_groups[normalized].append(query)

    analysis = {
        "total_queries": len(queries),
        "unique_queries": len(query_groups),
        "query_groups": {},
        "potential_n1": [],
        "recommendations": []
    }

    for normalized, group in query_groups.items():
        count = len(group)
        analysis["query_groups"][normalized] = {
            "count": count,
            "sample_statement": group[0]["statement"]
        }

        # Detectar posibles N+1
        if count > 3:  # Más de 3 queries similares pueden indicar N+1
            analysis["potential_n1"].append({
                "query": normalized,
                "count": count,
                "pattern": "repeated_similar_query"
            })

    # Generar recomendaciones
    if analysis["total_queries"] > 10:
        analysis["recommendations"].append("Alto número de queries - considerar optimización")

    if analysis["potential_n1"]:
        analysis["recommendations"].append("Posibles queries N+1 detectadas - usar joinedload/selectinload")

    if any("SELECT" in group and "JOIN" not in group for group in query_groups.keys()):
        analysis["recommendations"].append("Queries sin JOINs - considerar eager loading")

    return analysis

def normalize_query(statement: str) -> str:
    """Normaliza query removiendo valores específicos"""
    import re
    # Remover números específicos, strings, etc.
    normalized = re.sub(r'\b\d+\b', 'X', statement)
    normalized = re.sub(r"'[^']*'", "'X'", normalized)
    normalized = re.sub(r'"[^"]*"', '"X"', normalized)
    return normalized.strip()

async def main():
    """Función principal"""
    print("🔍 ANÁLISIS DE QUERIES DB POR ENDPOINT")
    print("=" * 50)

    # Endpoints que sabemos tienen datos
    endpoints_to_analyze = [
        "/api/especialidades",
        "/api/temas",
        "/health"
    ]

    results = []

    for endpoint in endpoints_to_analyze:
        try:
            result = await analyze_endpoint_queries(endpoint)
            results.append(result)

            print(f"\n📊 {endpoint}:")
            print(f"   Queries: {result['total_queries']}")
            print(f"   Latencia: {result.get('latency_ms', 'N/A')}ms")

            if result.get('analysis', {}).get('potential_n1'):
                print(f"   ⚠️  Posibles N+1: {len(result['analysis']['potential_n1'])}")

            if result.get('analysis', {}).get('recommendations'):
                print("   💡 Recomendaciones:")
                for rec in result['analysis']['recommendations']:
                    print(f"      • {rec}")

        except Exception as e:
            print(f"❌ Error analizando {endpoint}: {e}")

    # Guardar resultados
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = f"docs/backend/perf_history/query_analysis_{timestamp}.json"

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "analysis_results": results
        }, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Análisis guardado en: {output_file}")

    return results

if __name__ == "__main__":
    # Verificar que el backend esté corriendo
    try:
        import httpx
        response = httpx.get("http://127.0.0.1:8000/health", timeout=5.0)
        if response.status_code != 200:
            print("❌ Backend no responde correctamente")
            sys.exit(1)
    except Exception as e:
        print(f"❌ No se puede conectar al backend: {e}")
        print("   Asegúrate de que el backend esté corriendo en http://127.0.0.1:8000")
        sys.exit(1)

    asyncio.run(main())
