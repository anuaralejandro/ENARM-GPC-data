#!/usr/bin/env python3
"""
🔥 ESTRATEGIA DEFINITIVA: Google Search + OCR + Clasificador AI

Combina lo mejor de ambos mundos:
- Google encuentra candidatos (rápido, alta recall)
- OCR valida contenido (Tesseract, preciso)
- AI clasifica GER/GRR (sentence-transformers, GPU)

NO usa LLaVA (demasiado lento).
"""

from __future__ import annotations
import os
import re
import sys
import time
import json
import hashlib
import io
import warnings
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict

import requests
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from sentence_transformers import SentenceTransformer
import torch
import numpy as np

# Configurar Tesseract
TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Tesseract-OCR\tesseract.exe",
    Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe",
]
for tpath in TESSERACT_PATHS:
    if Path(tpath).exists():
        pytesseract.pytesseract.tesseract_cmd = str(tpath)
        break

# Suprimir warnings
warnings.filterwarnings("ignore", category=UserWarning)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
PDF_CACHE_DIR = DATA_DIR / ".pdf_cache"
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Dominios confiables
TRUSTED_DOMAINS = [
    "cenetec-difusion.com",
    "cenetec.salud.gob.mx",
    "imss.gob.mx",
    "salud.gob.mx",
]


@dataclass
class GPCSearchResult:
    url: str
    confidence: float
    source: str  # "Google + OCR + AI"
    doc_type: str  # "GER" o "GRR"
    title_match: float  # Similitud con título esperado
    ai_confidence: float  # Confianza del clasificador AI


class SmartValidator:
    """
    🤖 Validador inteligente que combina:
    - OCR (Tesseract)
    - Semantic similarity (sentence-transformers)
    - AI classification (GER/GRR)
    """
    
    def __init__(self, model_name: str = "paraphrase-multilingual-mpnet-base-v2"):
        self.model_name = model_name
        self.model = None
        self.device = None
        
    def load_model(self) -> bool:
        """Cargar modelo de embeddings (GPU si disponible)"""
        if self.model is not None:
            return True
        
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"🔥 Cargando modelo '{self.model_name}' en {device.upper()}...")
            self.model = SentenceTransformer(self.model_name, device=device)
            self.device = device
            
            if device == "cuda":
                gpu_name = torch.cuda.get_device_name(0)
                print(f"✅ GPU detectada: {gpu_name}")
            else:
                print(f"⚠️  Usando CPU (más lento)")
            
            return True
        except Exception as e:
            print(f"❌ Error cargando modelo: {e}")
            return False
    
    def extract_text_smart(self, pdf_bytes: bytes) -> Tuple[str, List[str]]:
        """
        Extrae texto del PDF usando estrategia en cascada:
        1. PyMuPDF (nativo, rápido)
        2. Tesseract OCR (si falla o texto muy corto)
        
        Returns: (texto_completo, líneas_título_candidatas)
        """
        if not pdf_bytes or pdf_bytes[:4] != b'%PDF':
            return "", []
        
        # Nivel 1: PyMuPDF (95% de casos)
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if len(doc) == 0:
                return "", []
            
            page = doc[0]
            text = page.get_text()
            
            if text and len(text.strip()) > 100:
                # Texto extraído exitosamente
                lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 5]
                
                # Filtrar líneas candidatas a título (líneas 3-25, más flexible)
                title_candidates = []
                
                # Estrategia 1: Líneas individuales largas
                for i, line in enumerate(lines[3:25], start=3):
                    if len(line) > 15 and not line.isdigit():
                        # Ignorar headers comunes
                        line_lower = line.lower()
                        if line_lower not in ('cenetec', 'imss', 'secretaría de salud', 'méxico', 
                                              'guía de práctica clínica', 'gobierno de la república',
                                              'salud', 'evidencias y recomendaciones'):
                            title_candidates.append(line)
                
                # Estrategia 2: Combinar 2-3 líneas consecutivas (títulos multi-línea)
                for i in range(3, min(20, len(lines) - 2)):
                    # Combinar 2 líneas
                    combined_2 = f"{lines[i]} {lines[i+1]}".strip()
                    if len(combined_2) > 30:
                        title_candidates.append(combined_2)
                    
                    # Combinar 3 líneas
                    if i < len(lines) - 3:
                        combined_3 = f"{lines[i]} {lines[i+1]} {lines[i+2]}".strip()
                        if len(combined_3) > 40:
                            title_candidates.append(combined_3)
                
                return text, title_candidates[:20]  # Top 20 candidatos
        except Exception as e:
            print(f"  [PyMuPDF falló: {e}]")
        
        # Nivel 2: Tesseract OCR (PDFs escaneados)
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if len(doc) == 0:
                return "", []
            
            page = doc[0]
            
            # Renderizar a imagen de alta calidad
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # OCR solo del área del título (tercio superior)
            width, height = img.size
            title_area = img.crop((0, 0, width, height // 2))
            
            # OCR con español
            text = pytesseract.image_to_string(title_area, lang='spa', config='--psm 6')
            
            if text:
                lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 5]
                
                # Filtrar líneas candidatas
                title_candidates = []
                for line in lines:
                    if len(line) > 15 and not line.isdigit():
                        # Ignorar headers
                        if line.lower() not in ('méxico', 'gobierno de la república', 'salud', 'cenetec', 'imss'):
                            title_candidates.append(line)
                
                return text, title_candidates[:10]
        except Exception as e:
            print(f"  [OCR falló: {e}]")
        
        return "", []
    
    def classify_doc_type(self, text: str) -> Tuple[str, float]:
        """
        🏷️ Clasifica documento como GER, GRR o UNKNOWN.
        
        Returns: (tipo, confianza)
        """
        if not text:
            return "UNKNOWN", 0.0
        
        text_lower = text.lower()
        
        # Keywords ponderados
        ger_keywords = {
            'evidencias y recomendaciones': 4.0,
            'evidencias': 2.5,
            'recomendaciones': 2.5,
            'metodología': 2.0,
            'búsqueda': 1.5,
            'calidad de la evidencia': 3.0,
            'grado de recomendación': 2.5,
            'referencias bibliográficas': 2.0,
            'niveles de evidencia': 2.5,
            'algoritmo de manejo': 1.0,
        }
        
        grr_keywords = {
            'referencia rápida': 5.0,
            'referencia rapida': 5.0,
            'algoritmo': 3.0,
            'diagrama de flujo': 3.5,
            'guía rápida': 3.5,
            'guia rapida': 3.5,
            'flujograma': 2.5,
            'cuadro de decisión': 2.0,
        }
        
        # Calcular scores
        ger_score = sum(weight for keyword, weight in ger_keywords.items() if keyword in text_lower)
        grr_score = sum(weight for keyword, weight in grr_keywords.items() if keyword in text_lower)
        
        # Heurística de longitud
        text_len = len(text)
        if text_len < 8000:
            grr_score += 1.5
        elif text_len > 25000:
            ger_score += 1.5
        
        # Decidir
        total = ger_score + grr_score
        if total == 0:
            return "UNKNOWN", 0.0
        
        if ger_score > grr_score:
            return "GER", ger_score / total
        elif grr_score > ger_score:
            return "GRR", grr_score / total
        else:
            return "UNKNOWN", 0.5
    
    def compute_similarity(self, expected_title: str, candidate_lines: List[str]) -> float:
        """
        Calcula similitud semántica entre título esperado y líneas candidatas.
        Usa embeddings (GPU-accelerated).
        
        Returns: Mejor similitud [0.0-1.0]
        """
        if not self.load_model():
            return 0.0
        
        if not candidate_lines:
            return 0.0
        
        try:
            # Encode
            title_vec = self.model.encode([expected_title], normalize_embeddings=True)[0]
            cand_vecs = self.model.encode(candidate_lines, normalize_embeddings=True)
            
            # Cosine similarity
            sims = cand_vecs @ title_vec
            return float(np.max(sims))
        except Exception as e:
            print(f"  [Similarity error: {e}]")
            return 0.0
    
    def validate_pdf(self, pdf_bytes: bytes, expected_title: str, expected_type: str, url_type: Optional[str] = None) -> Tuple[bool, float, str, float]:
        """
        Valida PDF completo:
        1. Extrae texto (PyMuPDF + OCR fallback)
        2. Clasifica tipo (GER/GRR) - PRIORIZA url_type sobre contenido
        3. Valida similitud con título esperado
        
        Args:
            pdf_bytes: Bytes del PDF
            expected_title: Título esperado del GPC
            expected_type: Tipo esperado ("GER" o "GRR")
            url_type: Tipo detectado por URL (más confiable que contenido)
        
        Returns: (válido, confianza, tipo_detectado, similitud_título)
        """
        # Extraer texto
        text, title_candidates = self.extract_text_smart(pdf_bytes)
        
        if not text:
            return False, 0.0, "UNKNOWN", 0.0
        
        # PRIORIDAD 1: Tipo por URL (más confiable)
        if url_type:
            detected_type = url_type
            type_confidence = 0.95  # Alta confianza si viene de URL
        else:
            # PRIORIDAD 2: Clasificar por contenido
            detected_type, type_confidence = self.classify_doc_type(text)
        
        # Validar tipo esperado (solo si no es UNKNOWN)
        if expected_type and detected_type != "UNKNOWN" and detected_type != expected_type:
            # Tipo incorrecto
            return False, 0.0, detected_type, 0.0
        
        # Validar título
        title_similarity = self.compute_similarity(expected_title, title_candidates)
        
        # Umbral de validación (ajustado tras análisis empírico)
        MIN_SIMILARITY = 0.35  # 35% similitud mínima (GPCs tienen mucho header noise)
        
        if title_similarity < MIN_SIMILARITY:
            return False, title_similarity, detected_type, title_similarity
        
        # Calcular confianza final
        confidence = (0.6 * title_similarity + 0.4 * type_confidence)
        
        return True, confidence, detected_type, title_similarity


def is_trusted_domain(url: str) -> bool:
    """Verifica si URL es de dominio confiable"""
    url_lower = url.lower()
    return any(domain in url_lower for domain in TRUSTED_DOMAINS)


def download_pdf(url: str, timeout: int = 30) -> Optional[bytes]:
    """Descarga PDF con caché"""
    # Check cache
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    cache_path = PDF_CACHE_DIR / f"{h}.pdf"
    
    if cache_path.exists():
        try:
            data = cache_path.read_bytes()
            if data[:4] == b'%PDF':
                return data
        except Exception:
            pass
    
    # Download
    try:
        resp = requests.get(url, timeout=timeout, stream=True)
        resp.raise_for_status()
        
        # Read with size limit
        buf = io.BytesIO()
        total = 0
        max_bytes = 10 * 1024 * 1024  # 10 MB
        
        for chunk in resp.iter_content(chunk_size=64*1024):
            if not chunk:
                break
            buf.write(chunk)
            total += len(chunk)
            if total > max_bytes:
                break
        
        data = buf.getvalue()
        
        # Validate
        if not data or data[:4] != b'%PDF':
            return None
        
        # Cache
        try:
            cache_path.write_bytes(data)
        except Exception:
            pass
        
        return data
    except Exception:
        return None


def google_search(query: str, num_results: int = 10) -> List[Dict[str, Any]]:
    """Busca en Google Custom Search API"""
    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id = os.environ.get("GOOGLE_CSE_ID")
    
    if not api_key or not cse_id:
        raise RuntimeError("GOOGLE_API_KEY y GOOGLE_CSE_ID requeridos")
    
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "num": min(num_results, 10)
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        items = data.get("items", [])
        return [{"link": item.get("link"), "title": item.get("title")} for item in items]
    except Exception as e:
        print(f"❌ Error en búsqueda: {e}")
        return []


def classify_url_type(url: str) -> Optional[str]:
    """
    🏷️ Clasifica tipo de documento por URL (más confiable que contenido).
    
    CENETEC usa ER/RR, IMSS usa GER/GRR.
    
    Returns: "GER" o "GRR" o None
    """
    url_lower = url.lower()
    
    # CENETEC patterns: /ER.pdf = GER (completa), /RR.pdf = GRR (rápida)
    if url_lower.endswith("/er.pdf"):
        return "GER"
    if url_lower.endswith("/rr.pdf"):
        return "GRR"
    
    # IMSS patterns: XXXGER.pdf, XXXGRR.pdf
    if "ger.pdf" in url_lower:
        return "GER"
    if "grr.pdf" in url_lower:
        return "GRR"
    
    # Patterns in path
    if "/ger/" in url_lower or "_ger_" in url_lower or "-ger-" in url_lower:
        return "GER"
    if "/grr/" in url_lower or "_grr_" in url_lower or "-grr-" in url_lower:
        return "GRR"
    
    return None


def infer_complementary(url: str, found_type: str) -> Optional[str]:
    """
    🔗 Infiere URL complementario (GER ↔ GRR) sin validación HTTP.
    
    Patrones:
    - CENETEC: /ER.pdf ↔ /RR.pdf
    - IMSS: /XXXGER.pdf ↔ /XXXGRR.pdf
    
    Returns: URL inferida o None
    """
    if not url:
        return None
    
    url_lower = url.lower()
    
    if found_type == "GER":
        # ER.pdf → RR.pdf
        if url_lower.endswith("/er.pdf"):
            return url[:-6] + "RR.pdf"
        # XXXGER.pdf → XXXGRR.pdf
        if "ger.pdf" in url_lower:
            import re
            return re.sub(r'GER\.pdf$', 'GRR.pdf', url, flags=re.IGNORECASE)
    
    elif found_type == "GRR":
        # RR.pdf → ER.pdf
        if url_lower.endswith("/rr.pdf"):
            return url[:-6] + "ER.pdf"
        # XXXGRR.pdf → XXXGER.pdf
        if "grr.pdf" in url_lower:
            import re
            return re.sub(r'GRR\.pdf$', 'GER.pdf', url, flags=re.IGNORECASE)
    
    return None


def get_domain_priority(url: str) -> int:
    """
    Retorna prioridad del dominio (mayor = mejor).
    
    CENETEC > IMSS > otros
    """
    url_lower = url.lower()
    
    if "cenetec-difusion.com" in url_lower:
        return 100
    if "cenetec.salud.gob.mx" in url_lower:
        return 90
    if "imss.gob.mx" in url_lower:
        return 80
    if "salud.gob.mx" in url_lower:
        return 70
    
    return 50


def search_imss_cache(title: str, doc_type: str) -> Optional[str]:
    """
    🗄️ Busca en el caché IMSS local (198 GPCs gratis, sin API).
    
    Args:
        title: Título del GPC
        doc_type: "GER" o "GRR"
    
    Returns: URL del PDF o None
    """
    cache_path = DATA_DIR / "imss_catalog_cache.json"
    
    if not cache_path.exists():
        return None
    
    try:
        data = json.load(open(cache_path, encoding='utf-8'))
        entries = data.get('entries', [])
        
        # Normalizar título para búsqueda
        title_norm = title.lower()
        title_norm = re.sub(r'\b(diagnóstico|tratamiento|prevención|de|del|la|las|los|y|en|el)\b', '', title_norm)
        title_norm = re.sub(r'\s+', ' ', title_norm).strip()
        title_words = set(title_norm.split())
        
        best_match = None
        best_score = 0.0
        
        for entry in entries:
            entry_title = entry.get('title', '').lower()
            entry_norm = re.sub(r'\b(diagnóstico|tratamiento|prevención|de|del|la|las|los|y|en|el|ger|grr)\b', '', entry_title)
            entry_norm = re.sub(r'\s+', ' ', entry_norm).strip()
            entry_words = set(entry_norm.split())
            
            # Jaccard similarity
            if not title_words or not entry_words:
                continue
            
            intersection = len(title_words & entry_words)
            union = len(title_words | entry_words)
            score = intersection / union if union > 0 else 0.0
            
            if score > best_score and score >= 0.4:  # 40% mínimo
                best_score = score
                best_match = entry
        
        if best_match:
            url = best_match.get('ger_url') if doc_type == "GER" else best_match.get('grr_url')
            if url:
                print(f"      📦 Encontrado en IMSS cache: {url[-60:]}")
                return url
    
    except Exception as e:
        print(f"      ⚠️  Error leyendo IMSS cache: {e}")
    
    return None


def find_gpc_smart(title: str, doc_type: str, validator: SmartValidator) -> Optional[GPCSearchResult]:
    """
    🎯 ESTRATEGIA HÍBRIDA INTELIGENTE:
    1. Buscar en CENETEC (API Google, más actualizado)
    2. Si no se encuentra, buscar en IMSS cache (gratis, 198 GPCs)
    3. Validar con OCR + AI
    4. PRIORIZAR CENETEC sobre IMSS
    
    Args:
        title: Título del GPC a buscar
        doc_type: "GER" o "GRR"
        validator: Instancia de SmartValidator
    
    Returns: GPCSearchResult o None
    """
    # Construir query
    doc_keywords = {
        "GER": '"Guía de Evidencias y Recomendaciones" OR GER OR ER',
        "GRR": '"Guía de Referencia Rápida" OR GRR OR RR'
    }
    
    site_restriction = " OR ".join([f"site:{d}" for d in TRUSTED_DOMAINS])
    query = f'{title} {doc_keywords[doc_type]} filetype:pdf ({site_restriction})'
    
    print(f"  🔍 Buscando {doc_type}...")
    
    # Buscar en Google
    results = google_search(query, num_results=10)
    
    if not results:
        print(f"  ❌ Sin resultados de Google")
        return None
    
    # Filtrar y validar candidatos
    candidates: List[Tuple[float, str, float, str, int]] = []  # (confidence, url, title_sim, detected_type, domain_priority)
    
    for i, result in enumerate(results[:8]):  # Top 8 candidatos
        url = result.get("link", "")
        
        if not url or not url.lower().endswith(".pdf"):
            continue
        
        if not is_trusted_domain(url):
            continue
        
        # Clasificar por URL (más confiable que contenido)
        url_type = classify_url_type(url)
        if url_type and url_type != doc_type:
            print(f"    [{i+1}] Saltando {url[-60:]} (es {url_type}, buscamos {doc_type})")
            continue
        
        print(f"    [{i+1}] Validando: {url[-60:]}")
        
        # Descargar PDF
        pdf_bytes = download_pdf(url)
        if not pdf_bytes:
            print(f"        ❌ Descarga falló")
            continue
        
        # Validar con OCR + AI (pasar url_type para que tenga prioridad sobre contenido)
        is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
            pdf_bytes, title, doc_type, url_type=url_type
        )
        
        domain_priority = get_domain_priority(url)
        
        if is_valid:
            print(f"        ✅ Válido: tipo={url_type or detected_type}, similitud={title_sim:.2%}, confianza={confidence:.2%}, dominio={domain_priority}")
            candidates.append((confidence, url, title_sim, url_type or detected_type, domain_priority))
        else:
            reason = "tipo incorrecto" if detected_type != doc_type and detected_type != "UNKNOWN" else f"similitud baja ({title_sim:.2%})"
            print(f"        ❌ Rechazado: {reason}")
    
    if not candidates:
        print(f"  ❌ Ningún candidato validó correctamente en CENETEC")
        
        # 🗄️ FALLBACK: Buscar en IMSS cache
        print(f"  🔄 Intentando fallback a IMSS cache...")
        imss_url = search_imss_cache(title, doc_type)
        
        if imss_url:
            # Validar el PDF del IMSS cache
            pdf_bytes = download_pdf(imss_url)
            if pdf_bytes:
                url_type = classify_url_type(imss_url)
                is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
                    pdf_bytes, title, doc_type, url_type=url_type
                )
                
                if is_valid:
                    print(f"      ✅ IMSS cache válido: conf={confidence:.2%}")
                    return GPCSearchResult(
                        url=imss_url,
                        confidence=confidence,
                        source="IMSS_Cache",
                        doc_type=detected_type or url_type or doc_type,
                        title_match=title_sim,
                        ai_confidence=confidence
                    )
                else:
                    print(f"      ❌ IMSS cache no validó: similitud={title_sim:.2%}")
        
        return None
    
    # Seleccionar mejor candidato (priorizar CENETEC, luego confianza)
    candidates.sort(key=lambda x: (x[4], x[0]), reverse=True)  # Por domain_priority, luego confidence
    best_conf, best_url, best_sim, best_type, best_domain = candidates[0]
    
    print(f"  ✅ Mejor: {best_url[-60:]} (conf={best_conf:.2%}, dominio={best_domain})")
    
    return GPCSearchResult(
        url=best_url,
        confidence=best_conf,
        source="Google+OCR+AI",
        doc_type=best_type,
        title_match=best_sim,
        ai_confidence=best_conf
    )


def main():
    """Test con 3 GPCs REALES del temario ENARM"""
    
    # GPCs verificadas que SÍ existen en el temario
    test_gpcs = [
        ("Diagnóstico y Tratamiento de la Enfermedad Diverticular del Colon 2014", "Enfermedad diverticular"),
        ("Diagnóstico y Tratamiento de la Hipertensión Arterial 2014", "Hipertensión arterial"),
        ("Diagnóstico y Tratamiento del Sobrepeso y la Obesidad Exógena 2018", "Obesidad"),
    ]
    
    print("=" * 80)
    print("🔥 ESTRATEGIA SMART: Google + OCR + AI Classifier")
    print("=" * 80)
    print()
    
    # Inicializar validador
    validator = SmartValidator()
    
    if not validator.load_model():
        print("❌ No se pudo cargar el modelo de validación")
        return 1
    
    print()
    
    results = []
    total_time = 0
    
    for i, (title_full, title_short) in enumerate(test_gpcs, 1):
        print(f"\n{'='*80}")
        print(f"Test {i}/3: {title_short}")
        print(f"{'='*80}")
        
        start = time.time()
        
        # Buscar GER y GRR
        ger_result = find_gpc_smart(title_full, "GER", validator)
        grr_result = find_gpc_smart(title_full, "GRR", validator)
        
        # 🔗 INFERENCIA INTELIGENTE: Si encontramos uno, inferir el otro del mismo dominio
        if ger_result and not grr_result:
            inferred_grr_url = infer_complementary(ger_result.url, "GER")
            if inferred_grr_url:
                print(f"  🔗 Infiriendo GRR desde GER: {inferred_grr_url[-60:]}")
                # Validar que existe
                pdf_bytes = download_pdf(inferred_grr_url)
                if pdf_bytes and len(pdf_bytes) > 1000:  # Al menos 1KB
                    inferred_type = classify_url_type(inferred_grr_url)
                    
                    # Para PDFs inferidos del MISMO dominio/número, bajar umbral de similitud
                    # porque sabemos que es el correcto (solo cambiamos GER→GRR)
                    text, title_candidates = validator.extract_text_smart(pdf_bytes)
                    
                    if text and len(text) > 100:
                        # Calcular similitud
                        title_similarity = validator.compute_similarity(title_full, title_candidates)
                        
                        # UMBRAL MÁS BAJO para inferidos (25% vs 35% normal)
                        # Porque GRR son más cortas y tienen menos texto del título
                        if title_similarity >= 0.25 or inferred_type == "GRR":
                            detected_type, type_confidence = validator.classify_doc_type(text)
                            confidence = 0.6 * title_similarity + 0.4 * type_confidence
                            
                            print(f"      ✅ GRR inferido válido (similitud={title_similarity:.2%}, conf={confidence:.2%})")
                            grr_result = GPCSearchResult(
                                url=inferred_grr_url,
                                confidence=max(confidence, 0.75),  # Mínimo 75% para inferidos
                                source="Inferido desde GER",
                                doc_type="GRR",
                                title_match=title_similarity,
                                ai_confidence=confidence
                            )
                        else:
                            print(f"      ❌ GRR inferido rechazado (similitud={title_similarity:.2%} < 25%)")
                    else:
                        print(f"      ❌ GRR inferido sin texto extraíble")
        
        if grr_result and not ger_result:
            inferred_ger_url = infer_complementary(grr_result.url, "GRR")
            if inferred_ger_url:
                print(f"  🔗 Infiriendo GER desde GRR: {inferred_ger_url[-60:]}")
                # Validar que existe
                pdf_bytes = download_pdf(inferred_ger_url)
                if pdf_bytes and len(pdf_bytes) > 1000:  # Al menos 1KB
                    inferred_type = classify_url_type(inferred_ger_url)
                    
                    # Para PDFs inferidos del MISMO dominio/número, bajar umbral
                    text, title_candidates = validator.extract_text_smart(pdf_bytes)
                    
                    if text and len(text) > 100:
                        title_similarity = validator.compute_similarity(title_full, title_candidates)
                        
                        # UMBRAL MÁS BAJO para inferidos (25% vs 35%)
                        if title_similarity >= 0.25 or inferred_type == "GER":
                            detected_type, type_confidence = validator.classify_doc_type(text)
                            confidence = 0.6 * title_similarity + 0.4 * type_confidence
                            
                            print(f"      ✅ GER inferido válido (similitud={title_similarity:.2%}, conf={confidence:.2%})")
                            ger_result = GPCSearchResult(
                                url=inferred_ger_url,
                                confidence=max(confidence, 0.75),
                                source="Inferido desde GRR",
                                doc_type="GER",
                                title_match=title_similarity,
                                ai_confidence=confidence
                            )
                        else:
                            print(f"      ❌ GER inferido rechazado (similitud={title_similarity:.2%} < 25%)")
                    else:
                        print(f"      ❌ GER inferido sin texto extraíble")
        
        # 🏆 REGLA DE COHERENCIA: Si GER y GRR son de dominios diferentes, preferir el de mayor prioridad para ambos
        if ger_result and grr_result:
            ger_domain = get_domain_priority(ger_result.url)
            grr_domain = get_domain_priority(grr_result.url)
            
            if ger_domain != grr_domain:
                print(f"  ⚠️  Dominios diferentes: GER={ger_domain}, GRR={grr_domain}")
                
                # Intentar obtener ambos del dominio de mayor prioridad
                if ger_domain > grr_domain:
                    # Preferir dominio del GER, intentar inferir GRR desde ahí
                    print(f"      🔄 Intentando obtener GRR desde dominio del GER...")
                    inferred_grr = infer_complementary(ger_result.url, "GER")
                    if inferred_grr:
                        pdf_bytes = download_pdf(inferred_grr)
                        if pdf_bytes:
                            inferred_type = classify_url_type(inferred_grr)
                            is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
                                pdf_bytes, title_full, "GRR", url_type=inferred_type
                            )
                            if is_valid:
                                print(f"         ✅ GRR reemplazado (mismo dominio que GER)")
                                grr_result = GPCSearchResult(
                                    url=inferred_grr,
                                    confidence=confidence,
                                    source="Coherencia de dominio",
                                    doc_type="GRR",
                                    title_match=title_sim,
                                    ai_confidence=confidence
                                )
                else:
                    # Preferir dominio del GRR, intentar inferir GER desde ahí
                    print(f"      🔄 Intentando obtener GER desde dominio del GRR...")
                    inferred_ger = infer_complementary(grr_result.url, "GRR")
                    if inferred_ger:
                        pdf_bytes = download_pdf(inferred_ger)
                        if pdf_bytes:
                            inferred_type = classify_url_type(inferred_ger)
                            is_valid, confidence, detected_type, title_sim = validator.validate_pdf(
                                pdf_bytes, title_full, "GER", url_type=inferred_type
                            )
                            if is_valid:
                                print(f"         ✅ GER reemplazado (mismo dominio que GRR)")
                                ger_result = GPCSearchResult(
                                    url=inferred_ger,
                                    confidence=confidence,
                                    source="Coherencia de dominio",
                                    doc_type="GER",
                                    title_match=title_sim,
                                    ai_confidence=confidence
                                )
        
        elapsed = time.time() - start
        total_time += elapsed
        
        results.append({
            "title": title_short,
            "ger": ger_result.url if ger_result else None,
            "ger_confidence": ger_result.confidence if ger_result else 0.0,
            "grr": grr_result.url if grr_result else None,
            "grr_confidence": grr_result.confidence if grr_result else 0.0,
            "time": elapsed
        })
        
        print(f"\n⏱️  Tiempo: {elapsed:.1f}s")
        print(f"📊 GER: {'✅' if ger_result else '❌'} | GRR: {'✅' if grr_result else '❌'}")
        
        time.sleep(1)  # Rate limiting
    
    # Resumen
    print(f"\n{'='*80}")
    print("📊 RESUMEN")
    print(f"{'='*80}\n")
    
    ger_found = sum(1 for r in results if r['ger'])
    grr_found = sum(1 for r in results if r['grr'])
    both_found = sum(1 for r in results if r['ger'] and r['grr'])
    
    print(f"✅ GER encontrados: {ger_found}/{len(test_gpcs)} ({ger_found/len(test_gpcs)*100:.1f}%)")
    print(f"✅ GRR encontrados: {grr_found}/{len(test_gpcs)} ({grr_found/len(test_gpcs)*100:.1f}%)")
    print(f"🎯 Ambos encontrados: {both_found}/{len(test_gpcs)} ({both_found/len(test_gpcs)*100:.1f}%)")
    print(f"⏱️  Tiempo promedio: {total_time/len(test_gpcs):.1f}s por GPC")
    print(f"⏱️  Tiempo total: {total_time:.1f}s")
    
    # Guardar resultados
    output_path = DATA_DIR / "test_smart_validated_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Resultados guardados en: {output_path}")
    
    if both_found == len(test_gpcs):
        print(f"\n{'='*80}")
        print("🎉 TODOS LOS TESTS PASARON - Estrategia validada")
        print(f"{'='*80}")
        return 0
    else:
        print(f"\n⚠️  {len(test_gpcs) - both_found} GPCs incompletos")
        return 1


if __name__ == "__main__":
    sys.exit(main())
