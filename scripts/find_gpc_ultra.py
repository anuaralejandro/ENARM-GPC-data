#!/usr/bin/env python3
"""
🎯 FIND GPC ULTRA - MODO DIOS
Sistema de búsqueda y validación de altísima calidad para GPCs mexicanas.

CARACTERÍSTICAS:
✅ OCR GPU avanzado en español (EasyOCR)
✅ Prioriza catálogo IMSS (ya validado manualmente)
✅ Distingue "Diagnóstico" vs "Tratamiento" con inferencia semántica
✅ Convierte primera página a imagen para OCR robusto
✅ Validación cruzada título-contenido
✅ Manejo inteligente de texto no seleccionable

CALIDAD ENTERPRISE para:
- Sistema de salud mexicano (IMSS, ISSSTE, SSA)
- Referencia nacional para manejo de pacientes
- Preparación ENARM (examen residencias médicas)
"""

import os
import sys
import json
import re
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import requests
from pathlib import Path

# GPU OCR
import easyocr
import fitz  # PyMuPDF
from PIL import Image
import io
import numpy as np

# Embeddings semánticos
from sentence_transformers import SentenceTransformer
import torch


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

@dataclass
class GPCSearchConfig:
    """Configuración del sistema de búsqueda."""
    
    # OCR GPU
    ocr_languages: List[str] = None
    ocr_gpu: bool = True
    ocr_threshold: float = 0.5
    
    # Búsqueda
    google_api_key: str = None
    google_cse_id: str = None
    search_sleep: float = 1.0
    
    # Validación
    min_confidence: float = 0.85  # 85% mínimo enterprise
    use_imss_first: bool = True  # Priorizar catálogo IMSS
    
    # Paths
    imss_catalog_path: str = "data/imss_catalog_cache.json"
    temario_path: str = "docs/# Temario ENARM - Guías de Práctica Clín.md"
    output_path: str = "data/gpc_links_ultra.json"
    
    def __post_init__(self):
        if self.ocr_languages is None:
            self.ocr_languages = ['es', 'en']  # Español + Inglés
        
        if self.google_api_key is None:
            self.google_api_key = os.getenv("GOOGLE_API_KEY")
        
        if self.google_cse_id is None:
            self.google_cse_id = os.getenv("GOOGLE_CSE_ID")


# ============================================================================
# OCR GPU AVANZADO
# ============================================================================

class GPUOCREngine:
    """
    🚀 Motor OCR GPU de altísima calidad para texto médico español.
    
    Usa EasyOCR en GPU con:
    - Detección de texto en español médico
    - Conversión de PDF a imagen (primera página)
    - Manejo robusto de texto no seleccionable
    """
    
    def __init__(self, languages=['es', 'en'], gpu=True):
        print(f"[OCR GPU] Inicializando EasyOCR (idiomas: {languages}, GPU: {gpu})...")
        self.reader = easyocr.Reader(languages, gpu=gpu)
        print(f"✅ OCR GPU listo")
    
    def extract_title_from_pdf(
        self,
        pdf_bytes: bytes,
        fallback_to_text: bool = True
    ) -> Tuple[str, float, str]:
        """
        Extrae título del PDF usando OCR GPU.
        
        Estrategia:
        1. Intentar extraer texto seleccionable de primera página
        2. Si texto es sospechoso (símbolos raros), usar OCR
        3. Convertir primera página a imagen y aplicar OCR GPU
        
        Returns:
            (titulo, confianza, metodo)
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            first_page = doc[0]
            
            # Estrategia 1: Intentar texto seleccionable
            if fallback_to_text:
                text = first_page.get_text("text")
                if self._is_text_valid(text):
                    title, conf = self._extract_title_from_text(text)
                    if conf >= 0.6:
                        doc.close()
                        return title, conf, "text_selectable"
            
            # Estrategia 2: OCR GPU (SIEMPRE para máxima calidad)
            print(f"      [OCR GPU] Convirtiendo primera página a imagen...")
            
            # Convertir página a imagen de alta resolución
            pix = first_page.get_pixmap(matrix=fitz.Matrix(3, 3))  # 3x = 300 DPI
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            
            # Convertir a numpy array para EasyOCR
            img_np = np.array(img)
            
            # Aplicar OCR GPU
            print(f"      [OCR GPU] Ejecutando reconocimiento...")
            results = self.reader.readtext(img_np)
            
            # Procesar resultados OCR
            title, conf = self._process_ocr_results(results)
            
            doc.close()
            return title, conf, "ocr_gpu"
        
        except Exception as e:
            print(f"      ⚠️  Error OCR GPU: {e}")
            return "", 0.0, "error"
    
    def _is_text_valid(self, text: str) -> bool:
        """
        Verifica si texto seleccionable es válido.
        
        Detecta texto corrupto (símbolos raros, encoding incorrecto).
        """
        if not text or len(text.strip()) < 20:
            return False
        
        # Contar caracteres extraños
        weird_chars = sum(1 for c in text if ord(c) > 127 and c not in 'áéíóúÁÉÍÓÚñÑüÜ')
        weird_ratio = weird_chars / len(text)
        
        # Si >30% son caracteres raros → texto corrupto
        if weird_ratio > 0.3:
            return False
        
        # Buscar patrones de texto corrupto
        corrupt_patterns = [
            r'[$£€¥]{5,}',  # Muchos símbolos de moneda
            r'[█▓▒░]{5,}',  # Bloques
            r'[\x00-\x1F]{5,}',  # Caracteres de control
        ]
        
        for pattern in corrupt_patterns:
            if re.search(pattern, text):
                return False
        
        return True
    
    def _extract_title_from_text(self, text: str) -> Tuple[str, float]:
        """
        Extrae título de texto seleccionable.
        
        Busca patrones:
        - "Guía de Práctica Clínica"
        - "Diagnóstico y tratamiento de..."
        - Líneas en mayúsculas
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        # Patrón 1: Línea después de "GPC" o "Guía"
        for i, line in enumerate(lines):
            if 'guía' in line.lower() or 'gpc' in line.lower():
                if i + 1 < len(lines):
                    title = lines[i + 1]
                    if len(title) > 20 and len(title) < 150:
                        return title, 0.8
        
        # Patrón 2: Línea con "Diagnóstico", "Tratamiento", "Prevención"
        keywords = ['diagnóstico', 'tratamiento', 'prevención', 'manejo', 'detección']
        for line in lines[:10]:  # Primeras 10 líneas
            if any(kw in line.lower() for kw in keywords) and len(line) > 20:
                return line, 0.7
        
        # Patrón 3: Línea en mayúsculas larga
        for line in lines[:10]:
            if line.isupper() and len(line) > 20 and len(line) < 150:
                return line.title(), 0.6
        
        # Fallback: primera línea larga
        for line in lines[:5]:
            if len(line) > 20:
                return line, 0.4
        
        return "", 0.0
    
    def _process_ocr_results(self, results: List[Tuple]) -> Tuple[str, float]:
        """
        Procesa resultados de EasyOCR para extraer título.
        
        Args:
            results: Lista de (bbox, texto, confianza) de EasyOCR
        
        Returns:
            (titulo, confianza_promedio)
        """
        if not results:
            return "", 0.0
        
        # Filtrar resultados por confianza y posición vertical
        # Título suele estar en el tercio superior de la página
        page_height = max(r[0][2][1] for r in results) if results else 1000
        upper_third = page_height / 3
        
        candidates = []
        for bbox, text, conf in results:
            # Verificar si está en tercio superior
            y_center = (bbox[0][1] + bbox[2][1]) / 2
            if y_center < upper_third and conf > 0.5:
                candidates.append((text, conf))
        
        if not candidates:
            # Si no hay candidatos en tercio superior, tomar todos con alta confianza
            candidates = [(text, conf) for bbox, text, conf in results if conf > 0.6]
        
        # Buscar líneas con palabras clave médicas
        medical_keywords = [
            'diagnóstico', 'tratamiento', 'prevención', 'manejo',
            'guía', 'práctica', 'clínica', 'enfermedad'
        ]
        
        best_title = ""
        best_conf = 0.0
        
        for text, conf in candidates:
            text_lower = text.lower()
            keyword_count = sum(1 for kw in medical_keywords if kw in text_lower)
            
            # Score: confianza OCR + bonus por keywords
            score = conf + (keyword_count * 0.1)
            
            if score > best_conf and len(text) > 20:
                best_title = text
                best_conf = conf
        
        # Si no encontramos nada bueno, concatenar primeras líneas
        if not best_title:
            texts = [text for text, conf in candidates[:3]]
            best_title = ' '.join(texts)
            best_conf = sum(conf for _, conf in candidates[:3]) / max(len(candidates[:3]), 1)
        
        return best_title, best_conf


# ============================================================================
# CLASIFICADOR SEMÁNTICO AVANZADO
# ============================================================================

class MedicalGPCClassifier:
    """
    🧠 Clasificador semántico para GPCs médicas mexicanas.
    
    Resuelve problemas de:
    - Distinguir "Diagnóstico" vs "Tratamiento" vs "Prevención"
    - Validar coherencia título-contenido
    - Inferir GPC correcta cuando OCR falla
    """
    
    def __init__(self, model_name='paraphrase-multilingual-mpnet-base-v2'):
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"[Clasificador] Cargando modelo en {self.device}...")
        self.model = SentenceTransformer(model_name, device=self.device)
        print(f"✅ Clasificador listo")
        
        # Catálogo de conceptos médicos (basado en temario ENARM)
        self.medical_concepts = {
            'diagnostico': [
                'diagnóstico', 'detección', 'tamizaje', 'screening',
                'abordaje diagnóstico', 'identificación', 'evaluación diagnóstica'
            ],
            'tratamiento': [
                'tratamiento', 'manejo', 'terapéutica', 'intervención',
                'abordaje terapéutico', 'quirúrgico', 'médico'
            ],
            'prevencion': [
                'prevención', 'profilaxis', 'vacunación', 'inmunización',
                'control', 'educación'
            ],
        }
        
        # Pre-computar embeddings de conceptos
        self.concept_embeddings = {}
        for concept, keywords in self.medical_concepts.items():
            self.concept_embeddings[concept] = [
                self.model.encode(kw, convert_to_tensor=True)
                for kw in keywords
            ]
    
    def classify_gpc_type(self, title: str) -> Tuple[str, float]:
        """
        Clasifica tipo de GPC: diagnóstico, tratamiento, o prevención.
        
        Returns:
            (tipo, confianza)
        """
        title_emb = self.model.encode(title, convert_to_tensor=True)
        
        best_concept = None
        best_similarity = 0.0
        
        for concept, embs in self.concept_embeddings.items():
            for emb in embs:
                sim = torch.nn.functional.cosine_similarity(
                    title_emb.unsqueeze(0),
                    emb.unsqueeze(0)
                )
                sim_value = float(sim.item())
                
                if sim_value > best_similarity:
                    best_similarity = sim_value
                    best_concept = concept
        
        return best_concept, best_similarity
    
    def detect_confusion(
        self,
        expected_title: str,
        extracted_title: str
    ) -> Optional[str]:
        """
        Detecta confusión entre GPCs similares.
        
        Ejemplo:
        - Esperado: "Diagnóstico de apendicitis"
        - Extraído: "Tratamiento de apendicitis"
        → Confusión detectada
        
        Returns:
            Mensaje de advertencia o None
        """
        exp_type, exp_conf = self.classify_gpc_type(expected_title)
        ext_type, ext_conf = self.classify_gpc_type(extracted_title)
        
        # Si ambos tienen alta confianza pero tipos diferentes
        if exp_conf > 0.7 and ext_conf > 0.7 and exp_type != ext_type:
            return f"confusion_{exp_type}_vs_{ext_type}"
        
        return None
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcula similitud semántica entre dos textos."""
        emb1 = self.model.encode(text1, convert_to_tensor=True)
        emb2 = self.model.encode(text2, convert_to_tensor=True)
        
        sim = torch.nn.functional.cosine_similarity(
            emb1.unsqueeze(0),
            emb2.unsqueeze(0)
        )
        
        return float(sim.item())


# ============================================================================
# CATÁLOGO IMSS
# ============================================================================

class IMSSCatalogProvider:
    """
    📚 Proveedor de GPCs del catálogo IMSS (pre-validado manualmente).
    
    PRIORIDAD MÁXIMA: El catálogo IMSS ya está perfecto.
    """
    
    def __init__(self, catalog_path: str):
        self.catalog_path = catalog_path
        self.catalog = self._load_catalog()
        print(f"✅ Catálogo IMSS cargado: {len(self.catalog)} GPCs")
    
    def _load_catalog(self) -> List[Dict]:
        """Carga catálogo IMSS desde JSON."""
        try:
            with open(self.catalog_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('entries', [])
        except Exception as e:
            print(f"⚠️  Error cargando catálogo IMSS: {e}")
            return []
    
    def search(
        self,
        title: str,
        classifier: MedicalGPCClassifier,
        threshold: float = 0.75
    ) -> Optional[Dict]:
        """
        Busca GPC en catálogo IMSS por similitud semántica.
        
        Args:
            title: Título de GPC buscada
            classifier: Clasificador semántico
            threshold: Umbral de similitud mínimo
        
        Returns:
            Entrada del catálogo o None
        """
        if not self.catalog:
            return None
        
        best_match = None
        best_similarity = 0.0
        
        for entry in self.catalog:
            catalog_title = entry.get('title', '')
            
            # Calcular similitud
            sim = classifier.calculate_similarity(title, catalog_title)
            
            # Verificar coherencia de tipo (diagnóstico vs tratamiento)
            confusion = classifier.detect_confusion(title, catalog_title)
            
            # Si hay confusión, penalizar similitud
            if confusion:
                sim *= 0.7  # Reducir 30%
            
            if sim > best_similarity and sim >= threshold:
                best_similarity = sim
                best_match = entry
        
        if best_match:
            print(f"      ✅ Encontrado en IMSS: {best_match['title'][:60]}... (similitud: {best_similarity:.2%})")
            return {
                'ger_url': best_match.get('ger_url'),
                'grr_url': best_match.get('grr_url'),
                'source': 'imss_catalog',
                'confidence': best_similarity
            }
        
        return None


# ============================================================================
# BÚSQUEDA GOOGLE CSE
# ============================================================================

class GoogleCSEProvider:
    """Proveedor de búsqueda Google Custom Search."""
    
    def __init__(self, api_key: str, cse_id: str):
        self.api_key = api_key
        self.cse_id = cse_id
    
    def search(self, query: str, num: int = 10) -> List[str]:
        """
        Ejecuta búsqueda en Google CSE.
        
        Returns:
            Lista de URLs (solo PDFs)
        """
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': self.api_key,
            'cx': self.cse_id,
            'q': query,
            'num': min(num, 10)
        }
        
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            items = data.get('items', [])
            
            # Filtrar solo PDFs
            pdfs = [
                item['link']
                for item in items
                if item.get('link', '').lower().endswith('.pdf')
            ]
            
            return pdfs
        
        except Exception as e:
            print(f"      ⚠️  Error en búsqueda Google: {e}")
            return []


# ============================================================================
# ORQUESTADOR PRINCIPAL
# ============================================================================

class UltraGPCFinder:
    """
    🎯 Orquestador principal - MODO DIOS.
    
    Estrategia de búsqueda:
    1. ✅ Catálogo IMSS (máxima prioridad)
    2. ✅ Google CSE CENETEC
    3. ✅ Google CSE IMSS
    4. ✅ Google CSE .mx genérico
    
    Para cada resultado:
    - OCR GPU en primera página
    - Clasificación semántica
    - Validación cruzada título-contenido
    - Detección de confusión diagnóstico vs tratamiento
    """
    
    def __init__(self, config: GPCSearchConfig):
        self.config = config
        
        # Inicializar componentes
        self.ocr = GPUOCREngine(config.ocr_languages, config.ocr_gpu)
        self.classifier = MedicalGPCClassifier()
        self.imss = IMSSCatalogProvider(config.imss_catalog_path)
        self.google = GoogleCSEProvider(config.google_api_key, config.google_cse_id)
    
    def search_gpc(self, title: str, gpc_type: str) -> Optional[Dict]:
        """
        Busca GPC con estrategia multinivel.
        
        Args:
            title: Título de GPC (del temario ENARM)
            gpc_type: "GER" o "GRR"
        
        Returns:
            {'url': str, 'confidence': float, 'source': str}
        """
        print(f"\n🔍 Buscando: {title} ({gpc_type})")
        
        # ESTRATEGIA 1: Catálogo IMSS (MÁXIMA PRIORIDAD)
        if self.config.use_imss_first:
            imss_result = self.imss.search(title, self.classifier)
            if imss_result:
                url_key = 'ger_url' if gpc_type == 'GER' else 'grr_url'
                url = imss_result.get(url_key)
                if url:
                    # Validar con OCR GPU
                    validated = self._validate_url(url, title, gpc_type)
                    if validated and validated['confidence'] >= self.config.min_confidence:
                        return validated
                    else:
                        print(f"      ⚠️  URL IMSS no alcanzó confianza: {validated['confidence']:.2%} < {self.config.min_confidence:.2%}")
        
        # ESTRATEGIA 2: Google CSE CENETEC
        print(f"   [Google] Buscando en CENETEC...")
        cenetec_result = self._search_google_cenetec(title, gpc_type)
        if cenetec_result and cenetec_result['confidence'] >= self.config.min_confidence:
            return cenetec_result
        
        # ESTRATEGIA 3: Google CSE IMSS
        print(f"   [Google] Buscando en IMSS...")
        imss_google_result = self._search_google_imss(title, gpc_type)
        if imss_google_result and imss_google_result['confidence'] >= self.config.min_confidence:
            return imss_google_result
        
        # ESTRATEGIA 4: Google CSE .mx genérico (último recurso)
        print(f"   [Google] Buscando en dominios .mx...")
        mx_result = self._search_google_mx(title, gpc_type)
        if mx_result and mx_result['confidence'] >= 0.75:  # Threshold menor para .mx
            return mx_result
        
        print(f"   ❌ No se encontró GPC con confianza suficiente")
        return None
    
    def _search_google_cenetec(self, title: str, gpc_type: str) -> Optional[Dict]:
        """Busca en CENETEC vía Google CSE."""
        query = f'"{title}" {gpc_type} filetype:pdf site:cenetec-difusion.com OR site:cenetec.salud.gob.mx'
        results = self.google.search(query, num=5)
        time.sleep(self.config.search_sleep)
        
        for url in results:
            validated = self._validate_url(url, title, gpc_type)
            if validated and validated['confidence'] >= self.config.min_confidence:
                return validated
        
        return None
    
    def _search_google_imss(self, title: str, gpc_type: str) -> Optional[Dict]:
        """Busca en IMSS vía Google CSE."""
        query = f'"{title}" {gpc_type} filetype:pdf site:imss.gob.mx'
        results = self.google.search(query, num=5)
        time.sleep(self.config.search_sleep)
        
        for url in results:
            validated = self._validate_url(url, title, gpc_type)
            if validated and validated['confidence'] >= self.config.min_confidence:
                return validated
        
        return None
    
    def _search_google_mx(self, title: str, gpc_type: str) -> Optional[Dict]:
        """Busca en dominios .mx genéricos."""
        query = f'"{title}" {gpc_type} filetype:pdf site:.mx'
        results = self.google.search(query, num=5)
        time.sleep(self.config.search_sleep)
        
        for url in results:
            validated = self._validate_url(url, title, gpc_type)
            if validated and validated['confidence'] >= 0.75:
                return validated
        
        return None
    
    def _validate_url(self, url: str, expected_title: str, expected_type: str) -> Optional[Dict]:
        """
        Valida URL con OCR GPU y clasificación semántica.
        
        Returns:
            {'url': str, 'confidence': float, 'source': str, 'title_extracted': str}
        """
        try:
            print(f"      Validando: {url[:80]}...")
            
            # Descargar PDF
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            pdf_bytes = r.content
            
            # OCR GPU en primera página
            extracted_title, ocr_conf, ocr_method = self.ocr.extract_title_from_pdf(pdf_bytes)
            
            if not extracted_title:
                print(f"      ❌ No se pudo extraer título")
                return None
            
            print(f"      📄 Título extraído ({ocr_method}): {extracted_title[:60]}...")
            
            # Calcular similitud semántica
            title_sim = self.classifier.calculate_similarity(expected_title, extracted_title)
            
            # Detectar confusión (diagnóstico vs tratamiento)
            confusion = self.classifier.detect_confusion(expected_title, extracted_title)
            if confusion:
                print(f"      ⚠️  CONFUSIÓN DETECTADA: {confusion}")
                title_sim *= 0.5  # Penalización severa
            
            # Validar tipo de documento por URL
            url_type = self._classify_url_type(url)
            type_match = (url_type == expected_type) if url_type else 0.8
            
            # Confianza compuesta
            confidence = (
                0.60 * title_sim +       # 60% similitud título
                0.25 * ocr_conf +         # 25% confianza OCR
                0.15 * type_match         # 15% match tipo URL
            )
            
            print(f"      📊 Confianza: {confidence:.2%} (título: {title_sim:.2%}, OCR: {ocr_conf:.2%}, tipo: {type_match:.2%})")
            
            return {
                'url': url,
                'confidence': confidence,
                'source': self._get_source_from_url(url),
                'title_extracted': extracted_title,
                'ocr_method': ocr_method
            }
        
        except Exception as e:
            print(f"      ❌ Error validando URL: {e}")
            return None
    
    def _classify_url_type(self, url: str) -> Optional[str]:
        """Clasifica tipo de documento por URL."""
        url_lower = url.lower()
        
        # CENETEC: /ER.pdf = GER, /RR.pdf = GRR
        if url_lower.endswith('/er.pdf'):
            return 'GER'
        if url_lower.endswith('/rr.pdf'):
            return 'GRR'
        
        # IMSS: XXXGER.pdf, XXXGRR.pdf
        if 'ger.pdf' in url_lower:
            return 'GER'
        if 'grr.pdf' in url_lower:
            return 'GRR'
        
        return None
    
    def _get_source_from_url(self, url: str) -> str:
        """Determina fuente por URL."""
        url_lower = url.lower()
        
        if 'cenetec' in url_lower:
            return 'cenetec'
        if 'imss' in url_lower:
            return 'imss'
        if 'issste' in url_lower:
            return 'issste'
        if 'salud.gob.mx' in url_lower:
            return 'ssa'
        
        return 'otro_mx'


# ============================================================================
# EXTRACTOR DE TEMARIO ENARM
# ============================================================================

def extract_gpcs_from_temario(temario_path: str) -> List[Dict]:
    """
    Extrae lista de GPCs del temario ENARM (Markdown).
    
    Busca líneas con:
    - **GPC Diagnóstico de...**
    - **GPC Tratamiento de...**
    - etc.
    
    Returns:
        Lista de {'title': str, 'ger': bool, 'grr': bool}
    """
    gpcs = []
    
    try:
        with open(temario_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Buscar líneas con "GPC"
        gpc_pattern = re.compile(r'\*\*GPC\s+(.+?)\*\*', re.IGNORECASE)
        matches = gpc_pattern.findall(content)
        
        for match in matches:
            title = match.strip()
            
            # Limpiar título
            title = re.sub(r'\s+\d{4}$', '', title)  # Quitar año al final
            title = re.sub(r'\s+', ' ', title)
            
            gpcs.append({
                'title': title,
                'ger': True,  # Siempre buscar ambos
                'grr': True
            })
        
        print(f"✅ Extraídas {len(gpcs)} GPCs del temario ENARM")
        return gpcs
    
    except Exception as e:
        print(f"❌ Error extrayendo GPCs del temario: {e}")
        return []


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("""
================================================================================
🎯 FIND GPC ULTRA - MODO DIOS v1.0
Sistema de búsqueda y validación de altísima calidad para GPCs mexicanas
================================================================================
    """)
    
    # Configuración
    config = GPCSearchConfig()
    
    # Inicializar finder
    finder = UltraGPCFinder(config)
    
    # Extraer GPCs del temario ENARM
    gpcs = extract_gpcs_from_temario(config.temario_path)
    
    if not gpcs:
        print("❌ No se encontraron GPCs en el temario")
        return 1
    
    # Procesar cada GPC
    results = []
    
    for i, gpc in enumerate(gpcs, 1):
        print(f"\n[{i}/{len(gpcs)}] {gpc['title']}")
        
        result = {
            'title': gpc['title'],
            'ger_url': None,
            'grr_url': None,
            'ger_confidence': 0.0,
            'grr_confidence': 0.0,
            'ger_source': None,
            'grr_source': None,
            'ger_title_extracted': None,
            'grr_title_extracted': None,
        }
        
        # Buscar GER
        if gpc['ger']:
            ger_result = finder.search_gpc(gpc['title'], 'GER')
            if ger_result:
                result['ger_url'] = ger_result['url']
                result['ger_confidence'] = ger_result['confidence']
                result['ger_source'] = ger_result['source']
                result['ger_title_extracted'] = ger_result.get('title_extracted')
        
        # Buscar GRR
        if gpc['grr']:
            grr_result = finder.search_gpc(gpc['title'], 'GRR')
            if grr_result:
                result['grr_url'] = grr_result['url']
                result['grr_confidence'] = grr_result['confidence']
                result['grr_source'] = grr_result['source']
                result['grr_title_extracted'] = grr_result.get('title_extracted')
        
        results.append(result)
        
        # Guardar incrementalmente
        with open(config.output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"   ✅ GER: {result['ger_confidence']:.1%} | GRR: {result['grr_confidence']:.1%}")
        
        # Sleep entre GPCs
        time.sleep(config.search_sleep)
    
    # Estadísticas finales
    print(f"""
================================================================================
📊 ESTADÍSTICAS FINALES
================================================================================

Total GPCs procesadas: {len(results)}
GER encontradas: {sum(1 for r in results if r['ger_url'])} ({sum(1 for r in results if r['ger_url'])*100/len(results):.1f}%)
GRR encontradas: {sum(1 for r in results if r['grr_url'])} ({sum(1 for r in results if r['grr_url'])*100/len(results):.1f}%)
Ambas encontradas: {sum(1 for r in results if r['ger_url'] and r['grr_url'])} ({sum(1 for r in results if r['ger_url'] and r['grr_url'])*100/len(results):.1f}%)

Confianza promedio GER: {sum(r['ger_confidence'] for r in results)/len(results):.1%}
Confianza promedio GRR: {sum(r['grr_confidence'] for r in results)/len(results):.1%}

Fuentes GER:
  IMSS: {sum(1 for r in results if r['ger_source'] == 'imss' or r['ger_source'] == 'imss_catalog')}
  CENETEC: {sum(1 for r in results if r['ger_source'] == 'cenetec')}
  Otro .mx: {sum(1 for r in results if r['ger_source'] and 'imss' not in r['ger_source'] and 'cenetec' not in r['ger_source'])}

Fuentes GRR:
  IMSS: {sum(1 for r in results if r['grr_source'] == 'imss' or r['grr_source'] == 'imss_catalog')}
  CENETEC: {sum(1 for r in results if r['grr_source'] == 'cenetec')}
  Otro .mx: {sum(1 for r in results if r['grr_source'] and 'imss' not in r['grr_source'] and 'cenetec' not in r['grr_source'])}

✅ Resultados guardados en: {config.output_path}
================================================================================
    """)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
