#!/usr/bin/env python3
"""
Script para verificar y optimizar índices de base de datos
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from backend.database import get_database_url
import time

def check_existing_indexes():
    """Verifica qué índices existen actualmente en la base de datos"""
    print("🔍 VERIFICANDO ÍNDICES EXISTENTES")
    print("=" * 50)

    engine = create_engine(get_database_url())

    try:
        with engine.connect() as conn:
            # Query para obtener todos los índices (PostgreSQL)
            result = conn.execute(text("""
                SELECT
                    schemaname,
                    tablename,
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                AND indexname NOT LIKE '%_pkey'  -- Excluir primary keys
                ORDER BY tablename, indexname;
            """))

            indexes = result.fetchall()

            if not indexes:
                print("❌ No se encontraron índices personalizados")
                return []

            print(f"✅ Encontrados {len(indexes)} índices personalizados:")
            print()

            # Agrupar por tabla
            tables = {}
            for index in indexes:
                table = index.tablename
                if table not in tables:
                    tables[table] = []
                tables[table].append(index)

            for table_name, table_indexes in tables.items():
                print(f"📊 Tabla: {table_name}")
                for idx in table_indexes:
                    print(f"   • {idx.indexname}")
                print()

            return indexes

    except Exception as e:
        print(f"❌ Error verificando índices: {e}")
        return []

def get_recommended_indexes():
    """Retorna lista de índices recomendados para optimización"""
    return [
        {
            "name": "idx_usuarios_uid",
            "table": "usuarios",
            "column": "uid",
            "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usuarios_uid ON usuarios (uid);",
            "reason": "Búsquedas frecuentes por UID de usuario"
        },
        {
            "name": "idx_preguntas_dificultad",
            "table": "preguntas",
            "column": "dificultad",
            "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_preguntas_dificultad ON preguntas (dificultad);",
            "reason": "Filtros por dificultad en generación de tests"
        },
        {
            "name": "idx_usuarios_tests_status",
            "table": "usuarios_tests",
            "column": "status",
            "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usuarios_tests_status ON usuarios_tests (status);",
            "reason": "Filtros por estado de tests (activo, finalizado)"
        },
        {
            "name": "idx_usuarios_tests_created_at",
            "table": "usuarios_tests",
            "column": "created_at",
            "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usuarios_tests_created_at ON usuarios_tests (created_at);",
            "reason": "Ordenamiento cronológico de tests"
        },
        {
            "name": "idx_preguntas_caso_clinico_orden",
            "table": "preguntas",
            "column": "caso_clinico_id_fk, orden_en_caso",
            "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_preguntas_caso_clinico_orden ON preguntas (caso_clinico_id_fk, orden_en_caso) WHERE caso_clinico_id_fk IS NOT NULL;",
            "reason": "Optimización de casos clínicos seriados"
        },
        {
            "name": "idx_usuarios_question_progress_composite",
            "table": "usuarios_question_progress",
            "column": "user_uid, status",
            "sql": "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usuarios_question_progress_composite ON usuarios_question_progress (user_uid, status);",
            "reason": "Consultas de progreso por usuario y estado"
        }
    ]

def check_missing_indexes(existing_indexes, recommended_indexes):
    """Identifica qué índices recomendados faltan"""
    existing_names = {idx.indexname for idx in existing_indexes}

    missing = []
    existing_recommended = []

    for rec_idx in recommended_indexes:
        if rec_idx["name"] in existing_names:
            existing_recommended.append(rec_idx)
        else:
            missing.append(rec_idx)

    return missing, existing_recommended

def analyze_query_performance():
    """Analiza rendimiento de queries comunes"""
    print("\n🔬 ANÁLISIS DE RENDIMIENTO DE QUERIES")
    print("=" * 50)

    engine = create_engine(get_database_url())

    # Queries comunes a analizar
    test_queries = [
        {
            "name": "Conteo especialidades",
            "sql": """
                EXPLAIN ANALYZE
                SELECT e.id, e.nombre, COUNT(p.id) as total_preguntas
                FROM especialidades e
                LEFT JOIN temas t ON e.id = t.especialidad_id
                LEFT JOIN preguntas p ON t.id = p.tema_id
                GROUP BY e.id, e.nombre;
            """
        },
        {
            "name": "Conteo temas",
            "sql": """
                EXPLAIN ANALYZE
                SELECT t.id, t.nombre, t.especialidad_id, COUNT(p.id) as total_preguntas
                FROM temas t
                LEFT JOIN preguntas p ON t.id = p.tema_id
                GROUP BY t.id, t.nombre, t.especialidad_id;
            """
        },
        {
            "name": "Búsqueda preguntas con filtros",
            "sql": """
                EXPLAIN ANALYZE
                SELECT p.id FROM preguntas p
                JOIN temas t ON p.tema_id = t.id
                WHERE p.dificultad = 'Intermedio'
                AND t.especialidad_id = 1
                LIMIT 10;
            """
        }
    ]

    try:
        with engine.connect() as conn:
            for query in test_queries:
                print(f"\n📊 {query['name']}:")
                try:
                    start_time = time.perf_counter()
                    result = conn.execute(text(query['sql']))
                    end_time = time.perf_counter()

                    execution_time = (end_time - start_time) * 1000
                    print(f"   ⏱️  Tiempo: {execution_time:.2f}ms")

                    # Obtener plan de ejecución
                    plan_lines = result.fetchall()

                    # Buscar información clave en el plan
                    total_cost = "N/A"
                    for line in plan_lines:
                        line_str = str(line[0]) if line else ""
                        if "cost=" in line_str:
                            # Extraer costo total
                            try:
                                cost_part = line_str.split("cost=")[1].split(")")[0]
                                if ".." in cost_part:
                                    total_cost = cost_part.split("..")[1]
                                    break
                            except:
                                pass

                    print(f"   💰 Costo estimado: {total_cost}")

                    # Detectar seq scans
                    seq_scans = sum(1 for line in plan_lines
                                  if "Seq Scan" in str(line[0]) if line)
                    if seq_scans > 0:
                        print(f"   ⚠️  Sequential scans: {seq_scans}")

                except Exception as e:
                    print(f"   ❌ Error: {e}")

    except Exception as e:
        print(f"❌ Error en análisis de queries: {e}")

def main():
    """Función principal"""
    print("🚀 VERIFICACIÓN Y OPTIMIZACIÓN DE ÍNDICES")
    print("=" * 60)

    # 1. Verificar índices existentes
    existing_indexes = check_existing_indexes()

    # 2. Obtener índices recomendados
    recommended_indexes = get_recommended_indexes()

    # 3. Identificar faltantes
    missing, existing_recommended = check_missing_indexes(existing_indexes, recommended_indexes)

    print("\n💡 RECOMENDACIONES DE ÍNDICES")
    print("=" * 50)

    if existing_recommended:
        print(f"✅ Índices recomendados ya implementados: {len(existing_recommended)}")
        for idx in existing_recommended:
            print(f"   • {idx['name']} en {idx['table']}")

    if missing:
        print(f"\n🔨 Índices recomendados faltantes: {len(missing)}")
        print("\nComandos SQL para ejecutar:")
        print("=" * 30)

        for idx in missing:
            print(f"\n-- {idx['reason']}")
            print(idx['sql'])
    else:
        print("\n🎉 ¡Todos los índices recomendados están implementados!")

    # 4. Análisis de rendimiento
    analyze_query_performance()

    print(f"\n📋 RESUMEN")
    print("=" * 50)
    print(f"✅ Índices existentes: {len(existing_indexes)}")
    print(f"💡 Índices recomendados implementados: {len(existing_recommended)}")
    print(f"🔨 Índices recomendados faltantes: {len(missing)}")

    if missing:
        print(f"\n🎯 SIGUIENTE PASO: Ejecutar los {len(missing)} comandos SQL mostrados arriba")
        print("   Usa CONCURRENTLY para evitar bloqueos en producción")
    else:
        print("\n🎉 BASE DE DATOS OPTIMIZADA - No se requieren índices adicionales")

    return len(missing) == 0

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"💥 Error inesperado: {e}")
        sys.exit(1)
